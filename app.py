from flask import Flask, request, render_template_string, send_file, session, jsonify
import csv, io, math, json, os, secrets, threading, time
from datetime import datetime

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0").lower() in ("1", "true", "yes")

# MVP hosting stores uploads in RAM, isolated by browser session. Use one Gunicorn
# worker (see Procfile) so every request for a session reaches the same store.
SESSION_DATA = {}
SESSION_LAST_SEEN = {}
DATA_LOCK = threading.RLock()
EMPTY_DATA = {"headers": [], "rows": [], "filename": "Data demo", "error": ""}

class SessionDataProxy:
    """Dictionary-like access to the active browser session's in-memory data."""
    def _data(self):
        sid = session.get("_ai_data_sid")
        if not sid:
            sid = secrets.token_urlsafe(24)
            session["_ai_data_sid"] = sid
        now = time.time()
        with DATA_LOCK:
            # Remove unused session datasets after 2 hours to limit RAM growth.
            stale = [key for key, last in SESSION_LAST_SEEN.items() if now - last > 7200]
            for key in stale:
                SESSION_LAST_SEEN.pop(key, None)
                SESSION_DATA.pop(key, None)
            if sid not in SESSION_DATA:
                SESSION_DATA[sid] = {"headers": [], "rows": [], "filename": "Data demo", "error": ""}
            SESSION_LAST_SEEN[sid] = now
            return SESSION_DATA[sid]

    def __getitem__(self, key):
        return self._data()[key]

    def __setitem__(self, key, value):
        self._data()[key] = value

    def update(self, *args, **kwargs):
        self._data().update(*args, **kwargs)

DATA = SessionDataProxy()

HTML = r"""
<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Data Analyst</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#141c30;--line:#293550;--muted:#9ba9c4;--text:#f3f6ff;--accent:#8b9cff;--green:#4adeb2;--red:#ff7d91}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top right,#222d58 0,#0b1020 45%);color:var(--text);font:15px system-ui,-apple-system,sans-serif}
main{max-width:1180px;margin:auto;padding:22px 16px 60px}.top{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
h1{font-size:clamp(25px,4vw,36px);margin:0;letter-spacing:-.8px}.sub{color:var(--muted);margin:8px 0 22px}
.panel{background:rgba(20,28,48,.94);border:1px solid var(--line);border-radius:16px;padding:16px;margin:14px 0}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{background:#10182b;border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}.metric small{color:var(--muted);display:block}.metric strong{font-size:24px;display:block;margin-top:7px;overflow-wrap:anywhere}
button,.btn{border:0;border-radius:10px;padding:11px 15px;background:var(--accent);color:#0b1020;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}
input,select{max-width:100%;padding:10px;border-radius:9px;border:1px solid var(--line);background:#0b1020;color:var(--text)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.muted{color:var(--muted)}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px}
.tablewrap{overflow:auto;max-height:430px;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left}th{position:sticky;top:0;background:#202b45}
.badge{padding:4px 8px;border-radius:20px;background:#293550;color:#dbe4ff}.bad{color:var(--red)}.good{color:var(--green)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}.notice{background:#182541;border-radius:10px;padding:12px;color:#dbe4ff}
svg{width:100%;height:auto;min-height:180px;background:#0d1527;border-radius:10px}.err{color:#ff9aa8}
@media(max-width:680px){main{padding:17px 11px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:1fr}.panel{padding:13px}.metric strong{font-size:21px}}
</style></head><body><main>
<div class="top"><div><h1>◈ AI Data Analyst</h1><div class="muted">Analisis • Prediksi • Deteksi anomali</div></div><span class="badge">Web • Termux</span></div>
<p class="sub">Unggah CSV untuk mengeksplorasi data, mendeteksi nilai tidak biasa, dan membuat prediksi baseline.</p>
<section class="panel"><h2>1. Masukkan data</h2>
<form method="post" action="/upload" enctype="multipart/form-data" class="row"><input type="file" name="file" accept=".csv,text/csv" required><button type="submit">Analisis CSV</button></form>
<p class="muted">Maksimal 12 MB. Untuk uji cepat, gunakan data demo atau unduh contoh CSV.</p>
<div class="row"><a class="btn" href="/demo">Gunakan data demo</a><a class="btn" href="/sample.csv" style="background:#263552;color:#eef2ff">Unduh contoh CSV</a></div>
{% if error %}<p class="err">{{error}}</p>{% endif %}
</section>
{% if headers %}
<section class="metrics">
<div class="metric"><small>Jumlah baris</small><strong>{{nrows}}</strong></div><div class="metric"><small>Jumlah kolom</small><strong>{{ncols}}</strong></div>
<div class="metric"><small>Sel kosong</small><strong>{{missing}}</strong></div><div class="metric"><small>Kolom numerik</small><strong>{{numeric|length}}</strong></div>
</section>
<section class="panel"><h2>2. Pratinjau data</h2><p class="muted">File: {{filename}}</p><div class="tablewrap"><table><thead><tr>{% for h in headers %}<th>{{h}}</th>{% endfor %}</tr></thead><tbody>
{% for row in preview %}<tr>{% for v in row %}<td>{{v}}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>
<h3>Kualitas data</h3><div class="tablewrap"><table><thead><tr><th>Kolom</th><th>Tipe terdeteksi</th><th>Kosong</th><th>Nilai unik</th></tr></thead><tbody>
{% for q in quality %}<tr><td>{{q.name}}</td><td>{{q.kind}}</td><td>{{q.missing}}</td><td>{{q.unique}}</td></tr>{% endfor %}
</tbody></table></div><a class="btn" href="/quality.csv">Unduh laporan kualitas CSV</a></section>
<section class="panel"><h2>3. Eksplorasi numerik</h2>
{% if numeric %}<form method="get" action="/" class="row"><label for="col">Kolom angka:</label><select id="col" name="col">{% for n in numeric %}<option value="{{n}}" {% if n==selected %}selected{% endif %}>{{n}}</option>{% endfor %}</select><button type="submit">Tampilkan</button></form>
{% if stats %}<div class="metrics" style="margin-top:12px"><div class="metric"><small>Rata-rata</small><strong>{{stats.mean}}</strong></div><div class="metric"><small>Median</small><strong>{{stats.median}}</strong></div><div class="metric"><small>Minimum</small><strong>{{stats.min}}</strong></div><div class="metric"><small>Maksimum</small><strong>{{stats.max}}</strong></div></div>
<h3>Grafik nilai per baris</h3>{{chart|safe}}{% endif %}{% else %}<p class="muted">Tidak ditemukan kolom numerik. Pastikan angka tidak tercampur teks.</p>{% endif %}
</section>
<section class="grid2"><div class="panel"><h2>4. Deteksi anomali</h2><p class="muted">Metode z-score menandai angka yang jauh dari rata-rata. Ini pemeriksaan awal, bukan bukti kesalahan.</p>
{% if numeric %}<form method="get" action="/" class="row"><input type="hidden" name="col" value="{{selected}}"><label>Ambang z-score</label><select name="threshold"><option value="2">2.0</option><option value="2.5" selected>2.5</option><option value="3">3.0</option></select><button>Deteksi</button></form>
<p><strong>{{anomaly_count}}</strong> baris terdeteksi anomali pada kolom {{selected}}.</p>
{% if anomalies %}<div class="tablewrap"><table><thead><tr><th>Baris</th><th>Nilai</th><th>Z-score</th></tr></thead><tbody>{% for a in anomalies %}<tr><td>{{a.index}}</td><td>{{a.value}}</td><td class="bad">{{a.z}}</td></tr>{% endfor %}</tbody></table></div>{% endif %}
<a class="btn" href="/anomalies.csv?col={{selected}}&threshold={{threshold}}">Unduh hasil anomali CSV</a>
{% else %}<p class="muted">Unggah kolom angka untuk menjalankan analisis.</p>{% endif %}</div>
<div class="panel"><h2>5. Prediksi baseline</h2><p class="muted">Regresi linear pada urutan baris. Cocok untuk demonstrasi, bukan untuk semua data musiman.</p>
{% if numeric %}<form method="get" action="/" class="row"><input type="hidden" name="col" value="{{selected}}"><label>Periode ke depan</label><select name="horizon">{% for h in [3,7,14,30] %}<option value="{{h}}" {% if h==horizon %}selected{% endif %}>{{h}}</option>{% endfor %}</select><button>Prediksi</button></form>
{% if forecast %}<p>Model: regresi linear sederhana.</p><div class="tablewrap"><table><thead><tr><th>Periode</th><th>Prediksi</th></tr></thead><tbody>{% for f in forecast %}<tr><td>{{f.period}}</td><td>{{f.value}}</td></tr>{% endfor %}</tbody></table></div><a class="btn" href="/forecast.csv?col={{selected}}&horizon={{horizon}}">Unduh prediksi CSV</a>{% endif %}
{% else %}<p class="muted">Unggah kolom angka untuk menjalankan prediksi.</p>{% endif %}</div></section>
{% endif %}
<footer class="muted" style="padding:18px 0">MVP demonstrasi lokal • Jangan unggah data rahasia ke server publik • Validasi model sebelum mengambil keputusan.</footer>
</main></body></html>
"""

def parse_csv(content):
    text = content.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    rows = list(csv.reader(io.StringIO(text), dialect))
    if len(rows) < 2: raise ValueError("CSV harus memiliki header dan minimal satu baris data.")
    headers = [h.strip() or f"kolom_{i+1}" for i,h in enumerate(rows[0])]
    if len(headers) > 100: raise ValueError("Terlalu banyak kolom (maksimal 100).")
    data=[]
    for row in rows[1:]:
        row=(row+[""]*len(headers))[:len(headers)]
        data.append([v.strip() for v in row])
    if len(data)>100000: raise ValueError("Maksimal 100.000 baris untuk MVP ini.")
    return headers, data

def numeric_values(col):
    vals=[]
    for i,row in enumerate(DATA["rows"]):
        try:
            v=float(row[col].replace(",",""))
            if math.isfinite(v): vals.append((i,v))
        except (ValueError,AttributeError): pass
    return vals

def number(v):
    return f"{v:,.3f}".rstrip("0").rstrip(".") if isinstance(v,(int,float)) else str(v)

def get_stats(values):
    xs=sorted(v for _,v in values); n=len(xs)
    if not n:return None
    mean=sum(xs)/n
    med=xs[n//2] if n%2 else (xs[n//2-1]+xs[n//2])/2
    return {"mean":number(mean),"median":number(med),"min":number(xs[0]),"max":number(xs[-1]),"mean_raw":mean}

def svg_chart(values):
    vals=[v for _,v in values][-120:]
    if len(vals)<2:return "<p class='muted'>Perlu minimal dua nilai numerik.</p>"
    w,h,pad=720,230,28; lo=min(vals); hi=max(vals)
    if hi==lo: hi=lo+1
    pts=[]
    for i,v in enumerate(vals):
        x=pad+i*(w-2*pad)/(len(vals)-1); y=h-pad-(v-lo)*(h-2*pad)/(hi-lo)
        pts.append(f"{x:.1f},{y:.1f}")
    return f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Grafik nilai'><line x1='{pad}' y1='{h-pad}' x2='{w-pad}' y2='{h-pad}' stroke='#53627d'/><polyline fill='none' stroke='#91a1ff' stroke-width='3' points='{' '.join(pts)}'/><text x='{pad}' y='18' fill='#9ba9c4' font-size='12'>{number(hi)}</text><text x='{pad}' y='{h-5}' fill='#9ba9c4' font-size='12'>{number(lo)}</text></svg>"

def forecast_values(values,horizon):
    # Ordinary least squares over valid observation indices; avoid third-party ML packages.
    if len(values)<3:return []
    xs=[i for i,_ in values]; ys=[v for _,v in values]
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    den=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den else 0.0
    intercept=my-slope*mx
    end=max(xs)
    return [{"period":f"+{i}","value":number(intercept+slope*(end+i))} for i in range(1,horizon+1)]

def anomaly_values(values, threshold):
    if len(values)<3:return []
    ys=[v for _,v in values]; mean=sum(ys)/len(ys)
    sd=(sum((v-mean)**2 for v in ys)/len(ys))**.5
    if sd==0:return []
    return [{"index":i+2,"value":number(v),"z":number((v-mean)/sd)} for i,v in values if abs((v-mean)/sd)>=threshold]

def render(error=""):
    headers=DATA["headers"]; rows=DATA["rows"]; numeric=[]
    for j,h in enumerate(headers):
        vals=numeric_values(j)
        if len(vals)>=3 and len(vals)/max(1,len(rows))>=0.6:numeric.append(h)
    selected=request.args.get("col")
    if selected not in numeric:selected=numeric[0] if numeric else None
    try: threshold=float(request.args.get("threshold","2.5"))
    except ValueError: threshold=2.5
    if threshold not in (2.0,2.5,3.0):threshold=2.5
    try:horizon=max(3,min(30,int(request.args.get("horizon","7"))))
    except ValueError:horizon=7
    stats=None; chart=""; anomalies=[]; forecast=[]; count=0
    if selected:
        vals=numeric_values(headers.index(selected)); stats=get_stats(vals); chart=svg_chart(vals)
        anomalies=anomaly_values(vals,threshold);count=len(anomalies)
        forecast=forecast_values(vals,horizon)
    quality=[]
    for j,h in enumerate(headers):
        vs=[r[j] for r in rows]; filled=[v for v in vs if v!=""]
        numeric_count=sum(1 for v in filled if _is_num(v))
        quality.append({"name":h,"kind":"numerik" if filled and numeric_count/len(filled)>=.6 else "teks/kategori",
                        "missing":len(vs)-len(filled),"unique":len(set(filled))})
    return render_template_string(HTML,headers=headers,rows=rows,preview=rows[:50],nrows=len(rows),ncols=len(headers),
        missing=sum(1 for r in rows for v in r if v==""),numeric=numeric,selected=selected,stats=stats,chart=chart,
        anomalies=anomalies,anomaly_count=count,threshold=threshold,horizon=horizon,forecast=forecast,quality=quality,
        filename=DATA["filename"],error=error)

def _is_num(v):
    try:return math.isfinite(float(v.replace(",","")))
    except (ValueError,AttributeError):return False

@app.route("/healthz")
def healthz():
    return jsonify(status="ok", app="AI Data Analyst"), 200

@app.route("/")
def index(): return render()

@app.route("/upload",methods=["POST"])
def upload():
    f=request.files.get("file")
    if not f or not f.filename:return render("Pilih file CSV terlebih dahulu.")
    if not f.filename.lower().endswith(".csv"):return render("Versi Termux ini menerima CSV. Simpan file Excel sebagai CSV UTF-8 dahulu.")
    try:
        headers,rows=parse_csv(f.read())
        DATA.update(headers=headers,rows=rows,filename=f.filename,error="")
        return render()
    except Exception as e:return render(f"CSV tidak dapat dibaca: {e}")

@app.route("/demo")
def demo():
    DATA.update(headers=["tanggal","penjualan","biaya","jumlah_pesanan"],rows=[],filename="data_demo.csv",error="")
    for i in range(90):
        sales=round(800+i*5+((i*37)%95)-45,2)
        if i==62:sales*=2.2
        DATA["rows"].append([f"2025-01-{(i%28)+1:02d}",str(sales),str(round(sales*.62+((i*11)%30),2)),str(12+(i*7)%43)])
    return render()

@app.route("/sample.csv")
def sample():
    content="tanggal,penjualan,biaya,jumlah_pesanan\n"+"".join(f"2025-01-{i%28+1:02d},{800+i*5},{500+i*3},{12+i%20}\n" for i in range(1,61))
    return send_file(io.BytesIO(content.encode()),mimetype="text/csv",as_attachment=True,download_name="contoh_data.csv")

@app.route("/quality.csv")
def quality_csv():
    out=io.StringIO(); w=csv.writer(out); w.writerow(["kolom","tipe","nilai_kosong","nilai_unik"])
    for j,h in enumerate(DATA["headers"]):
        vs=[r[j] for r in DATA["rows"]]; filled=[v for v in vs if v!=""]
        nc=sum(1 for v in filled if _is_num(v))
        w.writerow([h,"numerik" if filled and nc/len(filled)>=.6 else "teks/kategori",len(vs)-len(filled),len(set(filled))])
    return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")),mimetype="text/csv",as_attachment=True,download_name="laporan_kualitas.csv")

@app.route("/anomalies.csv")
def anomalies_csv():
    col=request.args.get("col","")
    if col not in DATA["headers"]:return "Kolom tidak valid",400
    try:t=float(request.args.get("threshold","2.5"))
    except ValueError:t=2.5
    if t not in (2.0,2.5,3.0):t=2.5
    vals=numeric_values(DATA["headers"].index(col)); ans=anomaly_values(vals,t)
    out=io.StringIO();w=csv.writer(out);w.writerow(["baris_data","nilai","z_score"])
    for a in ans:w.writerow([a["index"],a["value"],a["z"]])
    return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")),mimetype="text/csv",as_attachment=True,download_name="anomali.csv")

@app.route("/forecast.csv")
def forecast_csv():
    col=request.args.get("col","")
    if col not in DATA["headers"]:return "Kolom tidak valid",400
    try:h=max(3,min(30,int(request.args.get("horizon","7"))))
    except ValueError:h=7
    ans=forecast_values(numeric_values(DATA["headers"].index(col)),h)
    out=io.StringIO();w=csv.writer(out);w.writerow(["periode","prediksi"])
    for a in ans:w.writerow([a["period"],a["value"]])
    return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")),mimetype="text/csv",as_attachment=True,download_name="prediksi.csv")

if __name__ == "__main__":
    # Keep local Termux mode bound to localhost; Gunicorn binds the public service.
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
