#!/usr/bin/env python3
"""
MPU6050 Attitude Viewer - Web 版 (Flask + SocketIO)
在 Docker 或 Windows 執行，瀏覽器開 http://localhost:5000

Docker 執行:
  pip install flask flask-socketio pyserial
  python tool/mpu6050_web.py

  COM port (Windows): COM3 等
  Linux/Docker: /dev/ttyACM0 (需先用 usbipd-win 掛載 USB 裝置到 WSL2)

VS Code DevContainer 會自動 forward port 5000，Windows 瀏覽器直接開即可。
"""

import math
import re
import threading

import serial
import serial.tools.list_ports
from flask import Flask
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'px4-mpu6050'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

_ser      = None
_running  = False
_lock     = threading.Lock()


# ── Attitude math ──────────────────────────────────────────────────────────────

def accel_to_rp(ax, ay, az):
    roll  = math.degrees(math.atan2(ay, az))
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
    return roll, pitch


# ── Parser ─────────────────────────────────────────────────────────────────────

ACCEL_PAT = re.compile(
    r'sensor_accel.*?x:([-+]?\d+\.?\d*).*?y:([-+]?\d+\.?\d*).*?z:([-+]?\d+\.?\d*)', re.I)
GYRO_PAT  = re.compile(
    r'sensor_gyro.*?x:([-+]?\d+\.?\d*).*?y:([-+]?\d+\.?\d*).*?z:([-+]?\d+\.?\d*)', re.I)


class Parser:
    def __init__(self, cb):
        self._cb = cb
        self._gx = self._gy = self._gz = 0.0
        self._blk = None
        self._bx = self._by = self._bz = 0.0

    def feed(self, line):
        line = line.strip()
        m = ACCEL_PAT.search(line)
        if m:
            ax, ay, az = float(m[1]), float(m[2]), float(m[3])
            self._cb(*accel_to_rp(ax, ay, az), ax, ay, az,
                     self._gx, self._gy, self._gz)
            return
        m = GYRO_PAT.search(line)
        if m:
            self._gx, self._gy, self._gz = float(m[1]), float(m[2]), float(m[3])
            return
        ll = line.lower()
        if 'sensor_accel' in ll:
            self._blk = 'a'; self._bx = self._by = self._bz = 0.0; return
        if 'sensor_gyro' in ll:
            self._blk = 'g'; self._bx = self._by = self._bz = 0.0; return
        m2 = re.match(r'([xyz]):\s*([-+]?\d+\.?\d*)', line)
        if m2 and self._blk:
            v = float(m2[2])
            if   m2[1] == 'x': self._bx = v
            elif m2[1] == 'y': self._by = v
            elif m2[1] == 'z':
                self._bz = v
                if self._blk == 'a':
                    self._cb(*accel_to_rp(self._bx, self._by, self._bz),
                             self._bx, self._by, self._bz,
                             self._gx, self._gy, self._gz)
                elif self._blk == 'g':
                    self._gx, self._gy, self._gz = self._bx, self._by, self._bz
                self._blk = None


def _on_attitude(roll, pitch, ax, ay, az, gx, gy, gz):
    socketio.emit('attitude', dict(
        roll=roll, pitch=pitch,
        ax=ax, ay=ay, az=az,
        gx=gx, gy=gy, gz=gz,
    ))


_parser = Parser(_on_attitude)


# ── Serial RX thread ───────────────────────────────────────────────────────────

def _rx_loop():
    global _running, _ser
    while _running and _ser and _ser.is_open:
        try:
            data = _ser.read(512)
            if data:
                text = data.decode('utf-8', errors='replace')
                socketio.emit('log', {'text': text})
                for ln in text.splitlines():
                    _parser.feed(ln)
        except Exception:
            if _running:
                socketio.emit('log', {'text': '\n[Serial read error]\n'})
            break


# ── SocketIO events ────────────────────────────────────────────────────────────

@socketio.on('get_ports')
def handle_get_ports():
    ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
    result = []
    for p in ports:
        d = p.description or ''
        if d and d.lower() != p.device.lower() and p.device.lower() not in d.lower():
            label = f"{p.device}  [{d}]"
        else:
            label = p.device
        result.append({'device': p.device, 'label': label})
    emit('ports', result)


@socketio.on('connect_serial')
def handle_connect_serial(data):
    global _ser, _running, _parser
    with _lock:
        if _ser and _ser.is_open:
            emit('status', {'connected': True, 'msg': 'Already connected'})
            return
        try:
            port = data['port']
            baud = int(data['baud'])
            _ser = serial.Serial(port, baud, timeout=0.1)
            _running = True
            _parser = Parser(_on_attitude)
            threading.Thread(target=_rx_loop, daemon=True).start()
            emit('status', {'connected': True, 'port': port, 'baud': baud,
                            'msg': f'Connected to {port} @ {baud} bps'})
            socketio.emit('log', {'text': f'[Connected  {port} @ {baud} bps]\n'})
        except Exception as e:
            emit('status', {'connected': False, 'msg': str(e)})


@socketio.on('disconnect_serial')
def handle_disconnect_serial():
    global _ser, _running
    with _lock:
        _running = False
        if _ser:
            try:
                _ser.close()
            except Exception:
                pass
            _ser = None
        emit('status', {'connected': False, 'msg': 'Disconnected'})
        socketio.emit('log', {'text': '[Disconnected]\n'})


@socketio.on('send_cmd')
def handle_send_cmd(data):
    cmd = data.get('cmd', '').strip()
    if not cmd:
        return
    socketio.emit('log', {'text': f'> {cmd}\n'})
    if _ser and _ser.is_open:
        try:
            _ser.write((cmd + '\r\n').encode())
        except Exception as e:
            socketio.emit('log', {'text': f'[Send error: {e}]\n'})


# ── HTML (single-file, no external assets except socket.io CDN) ───────────────

HTML = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MPU6050 Attitude Viewer</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#14142a;color:#c0c0e0;font-family:Consolas,monospace;font-size:13px;
     height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* connection bar */
#conn{display:flex;align-items:center;gap:8px;padding:8px 12px;
      background:#1c1c38;border-bottom:1px solid #2a2a50;flex-shrink:0}
#conn select,#conn button{background:#252545;color:#c0c0e0;border:1px solid #3a3a60;
  padding:4px 8px;font-family:Consolas;font-size:12px;cursor:pointer}
#port{width:340px}
#baud{width:88px}
#cbtn{background:#003a22;color:#00ff88;font-weight:bold;padding:4px 14px}
#cbtn:hover,#cbtn.on:hover{background:#005533}
button:hover{background:#35355a}
#status{color:#cc4444}
#status.ok{color:#00cc66}

/* mid */
#mid{display:flex;flex:1;min-height:0}

/* horizon */
#hw{flex:3;display:flex;align-items:center;justify-content:center;padding:8px}
canvas{max-width:100%;max-height:100%}

/* data */
#dp{flex:2;padding:10px 14px;overflow-y:auto;border-left:1px solid #2a2a50}
.sec{color:#00cc66;font-weight:bold;margin-top:14px;margin-bottom:4px;font-size:11px}
.row{display:flex;margin:3px 0;align-items:baseline}
.lbl{width:60px;color:#909090}
.val{color:#FFD700;font-size:15px;font-weight:bold;width:96px}
.unit{color:#606080}

/* log */
#lp{height:185px;display:flex;flex-direction:column;border-top:1px solid #2a2a50;flex-shrink:0}
#lh{display:flex;align-items:center;padding:4px 10px;background:#1c1c38;gap:8px}
#lh span{color:#00cc66;font-weight:bold;flex:1}
#lh button{background:#252545;color:#c0c0e0;border:1px solid #3a3a60;padding:2px 10px;
  font-family:Consolas;font-size:11px;cursor:pointer}
#log{flex:1;background:#090918;color:#aaffaa;padding:6px;overflow-y:auto;
     white-space:pre-wrap;word-break:break-all;font-size:11px}
#ir{display:flex;padding:4px 8px;background:#0d0d20;gap:6px;border-top:1px solid #1c1c38}
#inp{flex:1;background:#090918;color:#aaffaa;border:1px solid #2a2a50;
     padding:3px 6px;font-family:Consolas;font-size:12px}
#ir button{background:#252545;color:#c0c0e0;border:1px solid #3a3a60;
  padding:3px 12px;font-family:Consolas;cursor:pointer}
</style>
</head>
<body>

<div id="conn">
  <label>Port:</label>
  <select id="port"></select>
  <select id="baud">
    <option>9600</option><option>19200</option><option>38400</option>
    <option selected>57600</option><option>115200</option>
    <option>230400</option><option>921600</option>
  </select>
  <button onclick="refreshPorts()" title="Refresh">⟳</button>
  <button id="cbtn" onclick="toggleConn()">Connect</button>
  <span id="status">● Disconnected</span>
</div>

<div id="mid">
  <div id="hw"><canvas id="c" width="400" height="400"></canvas></div>
  <div id="dp">
    <div class="sec">ATTITUDE</div>
    <div class="row"><span class="lbl">Roll</span><span class="val" id="v-roll">---</span><span class="unit"> °</span></div>
    <div class="row"><span class="lbl">Pitch</span><span class="val" id="v-pitch">---</span><span class="unit"> °</span></div>
    <div class="sec">ACCEL m/s²</div>
    <div class="row"><span class="lbl">X</span><span class="val" id="v-ax">---</span></div>
    <div class="row"><span class="lbl">Y</span><span class="val" id="v-ay">---</span></div>
    <div class="row"><span class="lbl">Z</span><span class="val" id="v-az">---</span></div>
    <div class="sec">GYRO rad/s</div>
    <div class="row"><span class="lbl">X</span><span class="val" id="v-gx">---</span></div>
    <div class="row"><span class="lbl">Y</span><span class="val" id="v-gy">---</span></div>
    <div class="row"><span class="lbl">Z</span><span class="val" id="v-gz">---</span></div>
  </div>
</div>

<div id="lp">
  <div id="lh">
    <span>Serial Log</span>
    <button onclick="copyLog()">Copy</button>
    <button onclick="clearLog()">Clear</button>
  </div>
  <div id="log"></div>
  <div id="ir">
    <input id="inp" placeholder="NSH command  e.g.  listener sensor_accel -n 1000"
           onkeydown="if(event.key==='Enter')sendCmd()">
    <button onclick="sendCmd()">Send</button>
  </div>
</div>

<script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
<script>
const socket = io();
let connected = false;
let roll = 0, pitch = 0;

/* ── ports ── */
function refreshPorts(){ socket.emit('get_ports'); }

socket.on('ports', ports => {
  const sel = document.getElementById('port');
  const cur = sel.value;
  sel.innerHTML = ports.map(p=>`<option value="${p.device}">${p.label}</option>`).join('');
  if(cur) sel.value = cur;
});

/* ── connect ── */
function toggleConn(){
  if(connected){ socket.emit('disconnect_serial'); }
  else { socket.emit('connect_serial',{port:document.getElementById('port').value,
                                        baud:document.getElementById('baud').value}); }
}

socket.on('status', d => {
  connected = d.connected;
  const btn=document.getElementById('cbtn'), st=document.getElementById('status');
  if(d.connected){
    btn.textContent='Disconnect'; btn.classList.add('on');
    st.textContent='● '+d.port; st.className='ok';
  } else {
    btn.textContent='Connect'; btn.classList.remove('on');
    st.textContent='● Disconnected'; st.className='';
  }
});

/* ── log ── */
socket.on('log', d => {
  const el=document.getElementById('log');
  el.textContent += d.text;
  if(el.textContent.length > 200000) el.textContent = el.textContent.slice(-150000);
  el.scrollTop = el.scrollHeight;
});
function copyLog(){ navigator.clipboard.writeText(document.getElementById('log').textContent); }
function clearLog(){ document.getElementById('log').textContent=''; }
function sendCmd(){
  const el=document.getElementById('inp'); const cmd=el.value.trim(); el.value='';
  if(cmd) socket.emit('send_cmd',{cmd});
}

/* ── attitude ── */
socket.on('attitude', d => {
  roll=d.roll; pitch=d.pitch;
  const p = v => (v>=0?'+':'')+v.toFixed(4);
  const a = v => (v>=0?'+':'')+v.toFixed(1);
  document.getElementById('v-roll').textContent  = a(d.roll);
  document.getElementById('v-pitch').textContent = a(d.pitch);
  ['ax','ay','az','gx','gy','gz'].forEach(k =>
    document.getElementById('v-'+k).textContent = p(d[k]));
});

/* ── horizon canvas ── */
const canvas=document.getElementById('c'), ctx=canvas.getContext('2d');

function resizeCanvas(){
  const hw=document.getElementById('hw');
  const s=Math.min(hw.clientWidth, hw.clientHeight)-16;
  canvas.width=s; canvas.height=s;
}

function drawHorizon(){
  const w=canvas.width, h=canvas.height, cx=w/2, cy=h/2, r=Math.min(w,h)/2-4;
  const rr=roll*Math.PI/180, pp=pitch*r/45;
  const hx=cx-pp*Math.sin(rr), hy=cy+pp*Math.cos(rr);
  const hdx=Math.cos(rr), hdy=-Math.sin(rr);
  const gdx=Math.sin(rr), gdy=Math.cos(rr);
  const ext=Math.max(w,h)*3;

  ctx.clearRect(0,0,w,h);

  /* circle clip */
  ctx.save();
  ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.clip();

  /* sky */
  ctx.fillStyle='#1a6b9a'; ctx.fillRect(0,0,w,h);

  /* ground */
  ctx.beginPath();
  ctx.moveTo(hx+hdx*ext+gdx*ext, hy+hdy*ext+gdy*ext);
  ctx.lineTo(hx-hdx*ext+gdx*ext, hy-hdy*ext+gdy*ext);
  ctx.lineTo(hx-hdx*ext, hy-hdy*ext);
  ctx.lineTo(hx+hdx*ext, hy+hdy*ext);
  ctx.closePath(); ctx.fillStyle='#643a12'; ctx.fill();

  /* pitch ladder */
  for(const deg of [-30,-20,-10,10,20,30]){
    const off=deg*r/45;
    const lhx=hx-off*Math.sin(rr), lhy=hy+off*Math.cos(rr);
    if(Math.hypot(lhx-cx,lhy-cy)>r*0.88) continue;
    const ll=Math.abs(deg)%20===0?r*0.40:r*0.24;
    ctx.beginPath(); ctx.moveTo(lhx+hdx*ll,lhy+hdy*ll); ctx.lineTo(lhx-hdx*ll,lhy-hdy*ll);
    ctx.strokeStyle='#d0d0d0'; ctx.lineWidth=1; ctx.stroke();
    ctx.fillStyle='#b0b0b0'; ctx.font=`${Math.max(9,r*0.07)|0}px Consolas`;
    ctx.fillText(Math.abs(deg), lhx+hdx*ll*1.15+gdx*3, lhy+hdy*ll*1.15+gdy*3+4);
  }

  /* horizon line */
  ctx.beginPath(); ctx.moveTo(hx+hdx*r*0.91,hy+hdy*r*0.91);
  ctx.lineTo(hx-hdx*r*0.91,hy-hdy*r*0.91);
  ctx.strokeStyle='white'; ctx.lineWidth=2; ctx.stroke();

  /* aircraft symbol */
  const sw=r*0.32, sh=8; ctx.strokeStyle='#FFD700'; ctx.lineWidth=3;
  [[cx-sw,cy,cx-sw*0.4,cy],[cx+sw*0.4,cy,cx+sw,cy],
   [cx-sw,cy,cx-sw,cy+sh],[cx+sw,cy,cx+sw,cy+sh]].forEach(([x1,y1,x2,y2])=>{
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  });
  ctx.fillStyle='#FFD700'; ctx.beginPath(); ctx.arc(cx,cy,4,0,Math.PI*2); ctx.fill();

  ctx.restore();

  /* roll ticks */
  for(let ang=-60;ang<=60;ang+=10){
    if(ang===0) continue;
    const ar=(ang-90)*Math.PI/180, tl=ang%30===0?10:5;
    ctx.beginPath();
    ctx.moveTo(cx+(r-2)*Math.cos(ar),cy+(r-2)*Math.sin(ar));
    ctx.lineTo(cx+(r-2-tl)*Math.cos(ar),cy+(r-2-tl)*Math.sin(ar));
    ctx.strokeStyle='#c0c0c0'; ctx.lineWidth=1; ctx.stroke();
  }

  /* 0° marker */
  ctx.beginPath(); ctx.moveTo(cx,cy-r+2); ctx.lineTo(cx,cy-r+14);
  ctx.strokeStyle='#FFD700'; ctx.lineWidth=2; ctx.stroke();

  /* roll pointer */
  const rpR=(roll-90)*Math.PI/180;
  const prx=cx+(r-14)*Math.cos(rpR), pry=cy+(r-14)*Math.sin(rpR);
  const pe=rpR+Math.PI/2;
  ctx.beginPath();
  ctx.moveTo(cx+(r-2)*Math.cos(rpR),cy+(r-2)*Math.sin(rpR));
  ctx.lineTo(prx+6*Math.cos(pe),pry+6*Math.sin(pe));
  ctx.lineTo(prx-6*Math.cos(pe),pry-6*Math.sin(pe));
  ctx.closePath(); ctx.fillStyle='#FFD700'; ctx.fill();

  /* border */
  ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2);
  ctx.strokeStyle='#00cc66'; ctx.lineWidth=2; ctx.stroke();
}

window.addEventListener('resize', ()=>{ resizeCanvas(); drawHorizon(); });
resizeCanvas();
setInterval(drawHorizon, 50);
refreshPorts();
</script>
</body>
</html>'''


@app.route('/')
def index():
    return HTML


if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"\n  MPU6050 Attitude Viewer  (Web 版)")
    print(f"  瀏覽器開啟: http://localhost:{port}\n")
    socketio.run(app, host='0.0.0.0', port=port,
                 debug=False, allow_unsafe_werkzeug=True)
