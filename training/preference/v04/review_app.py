"""Isolated local FastAPI app for blinded human design review."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from training.preference.v04.models import HumanReviewV1, ReviewSubmissionV1
from training.preference.v04.store import ReviewStore, resolve_approved_file


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reviewer_name: str = Field(min_length=1, max_length=100)


REVIEW_HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Design AI — Human Review</title><style>
:root{color-scheme:light dark;--bg:#171819;--panel:#242628;--text:#f2f1ed;--muted:#aaa;--line:#3b3e41;--accent:#d9b36c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,Segoe UI,sans-serif}
header{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:14px 24px;border-bottom:1px solid var(--line)}
main{max-width:1680px;margin:auto;padding:18px 24px 34px}.meta{text-align:center;max-width:1000px;margin:0 auto 14px}
.meta h1{font-size:18px;margin:0 0 5px}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.candidate{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;min-height:520px}
.candidate h2{text-align:center;margin:3px 0 9px;font-size:16px}.frame{height:64vh;display:grid;place-items:center;overflow:hidden;background:#d8d8d6;border-radius:6px}
.frame img{width:100%;height:100%;object-fit:contain;cursor:zoom-in}.actions{display:flex;flex-wrap:wrap;justify-content:center;gap:9px;margin:17px 0}
button{border:1px solid var(--line);background:#303337;color:var(--text);padding:11px 17px;border-radius:7px;font-weight:650;cursor:pointer}
button.primary{border-color:var(--accent)}button:hover{filter:brightness(1.16)}button:disabled{opacity:.45;cursor:not-allowed}
details{max-width:760px;margin:12px auto;background:var(--panel);padding:11px 14px;border-radius:8px}
.scores{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:12px}.scores label{font-size:12px;color:var(--muted)}
input,textarea,select{width:100%;background:#111;border:1px solid var(--line);color:var(--text);padding:8px;border-radius:5px}
textarea{min-height:60px;margin-top:10px}.login{position:fixed;inset:0;background:#111d;display:grid;place-items:center;z-index:5}
.login form{background:var(--panel);padding:26px;border-radius:10px;width:min(420px,90vw)}.login.hidden{display:none}
.zoom{display:none;position:fixed;inset:0;background:#000e;z-index:10;padding:22px}.zoom.open{display:grid;place-items:center}.zoom img{max-width:100%;max-height:100%;object-fit:contain}
#message{min-height:22px;text-align:center;color:var(--accent)}kbd{background:#333;padding:2px 6px;border-radius:4px;border:1px solid #555}
@media(max-width:850px){.grid{grid-template-columns:1fr}.frame{height:55vh}.scores{grid-template-columns:1fr 1fr}.candidate{min-height:0}}
</style></head><body>
<div id="login" class="login"><form id="loginForm"><h2>Bắt đầu review</h2><p class="muted">Nhập tên reviewer để lưu và tiếp tục phiên trước.</p><input id="reviewer" required maxlength="100" placeholder="Long / Designer_01"><button class="primary" type="submit" style="margin-top:12px">Bắt đầu</button></form></div>
<header><strong>Design AI · Human Review</strong><span id="progress">0 / 0</span><a href="/review/summary" style="color:var(--accent)">Tổng kết</a></header>
<main><section class="meta"><h1 id="brief">Đang tải…</h1><div class="muted"><span id="category"></span> · Reviewer: <span id="reviewerLabel"></span></div></section>
<section class="grid"><article class="candidate"><h2>DESIGN A</h2><div class="frame"><img id="imageA" alt="Design A"></div></article><article class="candidate"><h2>DESIGN B</h2><div class="frame"><img id="imageB" alt="Design B"></div></article></section>
<div class="actions"><button id="chooseA" class="primary">A đẹp hơn <kbd>A</kbd></button><button id="tie">Hòa <kbd>T</kbd></button><button id="chooseB" class="primary">B đẹp hơn <kbd>D/B</kbd></button><button id="bad">Cả hai xấu <kbd>X</kbd></button><button id="skip">Bỏ qua <kbd>S</kbd></button><button id="back">Quay lại</button></div>
<details><summary>Chấm điểm tùy chọn</summary><div class="scores" id="scores"></div><textarea id="notes" maxlength="2000" placeholder="Ghi chú ngắn (không bắt buộc)"></textarea><label class="muted">Độ tự tin (không bắt buộc)<select id="confidence"><option value="">—</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label></details>
<p id="message"></p><p class="muted" style="text-align:center">Chỉ hình ảnh, brief và category được hiển thị. Version/model/score được ẩn.</p></main>
<div id="zoom" class="zoom"><img id="zoomImage" alt="Phóng to"></div>
<script>
const byId=id=>document.getElementById(id);const login=byId('login'),loginForm=byId('loginForm'),reviewer=byId('reviewer'),reviewerLabel=byId('reviewerLabel'),brief=byId('brief'),category=byId('category'),imageA=byId('imageA'),imageB=byId('imageB'),progress=byId('progress'),scores=byId('scores'),notes=byId('notes'),confidence=byId('confidence'),message=byId('message'),chooseA=byId('chooseA'),chooseB=byId('chooseB'),tie=byId('tie'),bad=byId('bad'),skip=byId('skip'),back=byId('back'),zoom=byId('zoom'),zoomImage=byId('zoomImage');
let sessionId=null,current=null,busy=false;const dimensions=['composition','hierarchy','typography','brand_feeling','overall'];
const labels={composition:'Composition',hierarchy:'Hierarchy',typography:'Typography',brand_feeling:'Brand feeling',overall:'Overall'};
scores.innerHTML=dimensions.map(k=>`<label>${labels[k]}<select data-score="${k}"><option value="">—</option>${[1,2,3,4,5,6,7,8,9,10].map(n=>`<option>${n}</option>`).join('')}</select></label>`).join('');
function msg(v){message.textContent=v}function clearOptional(){document.querySelectorAll('[data-score]').forEach(x=>x.value='');notes.value='';confidence.value=''}
async function api(url,options={}){const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options});if(!response.ok)throw new Error((await response.json()).detail||response.statusText);return response.json()}
async function start(name){const data=await api('/api/v1/review/session',{method:'POST',body:JSON.stringify({reviewer_name:name})});sessionId=data.session_id;localStorage.setItem('reviewer',name);reviewerLabel.textContent=name;login.classList.add('hidden');await loadNext()}
function render(data){current=data.item;if(!current){brief.textContent='Phiên review đã hoàn tất';category.textContent='';imageA.removeAttribute('src');imageB.removeAttribute('src');document.querySelectorAll('.actions button:not(#back)').forEach(x=>x.disabled=true);msg('Cảm ơn bạn. Dữ liệu đã được lưu.');return}brief.textContent=current.brief;category.textContent=current.category;imageA.src=current.preview_a+'?v='+Date.now();imageB.src=current.preview_b+'?v='+Date.now();const p=current.progress;progress.textContent=`${p.completed} / ${p.total}${p.skipped?' · bỏ qua '+p.skipped:''}`;document.querySelectorAll('.actions button').forEach(x=>x.disabled=false);clearOptional();msg('')}
async function loadNext(){render(await api(`/api/v1/review/next?session_id=${encodeURIComponent(sessionId)}`))}
async function submit(choice){if(busy||!current)return;busy=true;try{const score={};document.querySelectorAll('[data-score]').forEach(x=>{if(x.value)score[x.dataset.score]=Number(x.value)});await api('/api/v1/review/submit',{method:'POST',body:JSON.stringify({session_id:sessionId,pair_id:current.pair_id,review:{choice,scores:Object.keys(score).length?score:null,notes:notes.value||null,confidence:confidence.value?Number(confidence.value):null}})});await loadNext()}catch(e){msg(e.message)}finally{busy=false}}
async function skipCurrent(){if(!current)return;await api('/api/v1/review/skip',{method:'POST',body:JSON.stringify({session_id:sessionId,pair_id:current.pair_id})});await loadNext()}
loginForm.onsubmit=e=>{e.preventDefault();start(reviewer.value.trim()).catch(e=>msg(e.message))};reviewer.value=localStorage.getItem('reviewer')||'';
chooseA.onclick=()=>submit('a');chooseB.onclick=()=>submit('b');tie.onclick=()=>submit('tie');bad.onclick=()=>submit('both_bad');skip.onclick=skipCurrent;
back.onclick=async()=>{if(!sessionId)return;const data=await api(`/api/v1/review/previous?session_id=${encodeURIComponent(sessionId)}`);if(data.item)render(data)};
document.onkeydown=e=>{if(login.classList.contains('hidden')&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){const k=e.key.toLowerCase();if(k==='a')submit('a');else if(k==='d'||k==='b')submit('b');else if(k==='t')submit('tie');else if(k==='x')submit('both_bad');else if(k==='s')skipCurrent()}};
[imageA,imageB].forEach(img=>img.onclick=()=>{zoomImage.src=img.src;zoom.classList.add('open')});zoom.onclick=()=>zoom.classList.remove('open');
</script></body></html>"""


SUMMARY_HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Review summary</title>
<style>body{font:16px system-ui;max-width:900px;margin:40px auto;padding:0 20px;background:#171819;color:#eee}pre{background:#25272a;padding:20px;border-radius:8px;white-space:pre-wrap}a{color:#d9b36c}</style></head>
<body><h1>Human Review Summary</h1><pre id="data">Đang tải…</pre><a href="/review">← Tiếp tục review</a>
<script>fetch('/api/v1/review/summary').then(r=>r.json()).then(x=>data.textContent=JSON.stringify(x,null,2))</script></body></html>"""


class SubmitEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    session_id: str
    pair_id: str
    review: ReviewSubmissionV1


class SkipEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    session_id: str
    pair_id: str


def create_review_app(store: ReviewStore) -> FastAPI:
    app = FastAPI(title="Design AI Human Review", version="0.4-phase1")

    def session(value: str):
        try:
            return store.load_session(value)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="review session not found") from exc

    @app.get("/review", response_class=HTMLResponse)
    def review_page() -> str:
        return REVIEW_HTML

    @app.get("/review/summary", response_class=HTMLResponse)
    def summary_page() -> str:
        return SUMMARY_HTML

    @app.post("/api/v1/review/session")
    def create_session(request: SessionRequest) -> dict:
        try:
            value = store.create_or_resume_session(request.reviewer_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"session_id": value.session_id, "reviewer": value.reviewer, "progress": store.progress(value)}

    @app.get("/api/v1/review/next")
    def next_review(session_id: str = Query(min_length=1)) -> dict:
        value = session(session_id)
        item = store.next_item(value)
        return {"item": store.public_item(value, item) if item else None, "progress": store.progress(value)}

    @app.get("/api/v1/review/previous")
    def previous_review(session_id: str = Query(min_length=1)) -> dict:
        value = session(session_id)
        item = store.previous_item(value)
        return {"item": store.public_item(value, item) if item else None, "progress": store.progress(value)}

    @app.get("/api/v1/review/progress")
    def progress(session_id: str = Query(min_length=1)) -> dict:
        return store.progress(session(session_id))

    @app.post("/api/v1/review/submit")
    def submit_review(request: SubmitEnvelope) -> dict:
        value = session(request.session_id)
        try:
            review = store.submit(session=value, pair_id=request.pair_id, submission=request.review)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"saved": True, "review_id": review.review_id, "progress": store.progress(value)}

    @app.post("/api/v1/review/skip")
    def skip_review(request: SkipEnvelope) -> dict:
        value = session(request.session_id)
        try:
            store.skip(value, request.pair_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"skipped": True, "progress": store.progress(value)}

    @app.get("/api/v1/review/preview/{session_id}/{pair_id}/{side}")
    def preview(session_id: str, pair_id: str, side: str) -> FileResponse:
        value = session(session_id)
        try:
            candidate = store.candidate_for_side(value, pair_id, side)
            path = resolve_approved_file(candidate.preview_path, store.approved_roots)
        except (KeyError, ValueError, PermissionError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="preview not found") from exc
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/review/summary")
    def review_summary() -> dict:
        reviews = []
        if store.reviews_dir.exists():
            for path in store.reviews_dir.rglob("*.json"):
                try:
                    reviews.append(HumanReviewV1.model_validate_json(path.read_text(encoding="utf-8")))
                except Exception:
                    continue
        choices = Counter(item.choice for item in reviews)
        return {
            "human_review_count": len(reviews),
            "a_wins": choices["a"], "b_wins": choices["b"],
            "ties": choices["tie"], "both_bad": choices["both_bad"],
            "category_distribution": dict(sorted(Counter(item.category for item in reviews).items())),
            "automated_preference_labels": 0,
        }

    return app
