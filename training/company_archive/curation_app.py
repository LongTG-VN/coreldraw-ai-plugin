"""Local minimal human curation UI for company archive previews."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from training.company_archive.curation import curate_file
from training.company_archive.database import ArchiveDatabase
from training.company_archive.models import (
    ArchiveCategory,
    GoldStatus,
    HumanQualityStatus,
    RightsStatus,
)


class CurateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    file_id: str
    reviewer: str = Field(min_length=1, max_length=100)
    quality: HumanQualityStatus
    category: ArchiveCategory | None = None
    certify_gold: bool = False
    confirm_company_rights: bool = False
    commercial_allowed: bool = False
    notes: str | None = Field(default=None, max_length=2000)


HTML = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Company CDR Gold Curation</title><style>body{margin:0;background:#171819;color:#eee;font:15px system-ui;display:grid;grid-template-rows:auto 1fr auto;min-height:100vh}header,footer{padding:14px 22px;background:#242628}main{padding:18px;display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:20px}.preview{display:grid;place-items:center;background:#333;min-height:65vh}.preview img{max-width:100%;max-height:75vh;object-fit:contain}.meta{background:#242628;padding:18px;border-radius:8px}button,select,input,textarea{width:100%;margin:6px 0;padding:10px;background:#111;color:#eee;border:1px solid #555;border-radius:6px}button{cursor:pointer;font-weight:700}.approve{border-color:#49a66c}.maybe{border-color:#c5a64d}.reject{border-color:#bd5b5b}.row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px}.muted{color:#aaa}@media(max-width:850px){main{grid-template-columns:1fr}}</style></head>
<body><header><strong>Company CDR · Human Gold Curation</strong> <span id="progress" class="muted"></span></header><main><div class="preview"><img id="image" alt="CDR preview"></div><aside class="meta"><h2 id="filename">Loading…</h2><pre id="facts"></pre><label>Reviewer<input id="reviewer" placeholder="Long / Designer_01"></label><label>Category<select id="category"><option value="">—</option></select></label><label><input id="rights" type="checkbox" style="width:auto"> Xác nhận quyền sở hữu/sử dụng của công ty</label><label><input id="gold" type="checkbox" style="width:auto"> Chứng nhận HUMAN_CERTIFIED_GOLD</label><label><input id="commercial" type="checkbox" style="width:auto"> Quyền commercial đã được xác nhận</label><textarea id="notes" placeholder="Ghi chú tùy chọn"></textarea><div class="row"><button class="approve" onclick="submit('APPROVE')">APPROVE</button><button class="maybe" onclick="submit('MAYBE')">MAYBE</button><button class="reject" onclick="submit('REJECT')">REJECT</button></div><p id="message"></p></aside></main><footer>Nút bấm là hành động con người. Không heuristic/model nào được promote Gold.</footer>
<script>const cats=['SALE','SPA','SIGNAGE','MENU','CAFE','BUSINESS_CARD','BANNER','LOGO','PRINT','OTHER'];category.innerHTML+=[...cats].map(x=>`<option>${x}</option>`).join('');reviewer.value=localStorage.getItem('company_reviewer')||'';let current=null;async function api(u,o={}){const r=await fetch(u,{headers:{'Content-Type':'application/json'},...o});if(!r.ok)throw Error((await r.json()).detail||r.statusText);return r.json()}async function next(){const d=await api('/api/v1/company-curation/next');current=d.item;if(!current){filename.textContent='Đã hết preview chưa review';image.removeAttribute('src');return}filename.textContent=current.filename;facts.textContent=JSON.stringify({dimensions:current.dimensions,page_count:current.page_count,object_count:current.object_count},null,2);image.src='/api/v1/company-curation/preview/'+encodeURIComponent(current.file_id);progress.textContent=d.progress}async function submit(q){if(!current)return;localStorage.setItem('company_reviewer',reviewer.value.trim());try{await api('/api/v1/company-curation/submit',{method:'POST',body:JSON.stringify({file_id:current.file_id,reviewer:reviewer.value.trim(),quality:q,category:category.value||null,certify_gold:gold.checked,confirm_company_rights:rights.checked,commercial_allowed:commercial.checked,notes:notes.value||null})});message.textContent='Đã lưu';gold.checked=rights.checked=commercial.checked=false;notes.value='';await next()}catch(e){message.textContent=e.message}}next().catch(e=>message.textContent=e.message)</script></body></html>"""


def create_curation_app(database: ArchiveDatabase, workspace: Path) -> FastAPI:
    app = FastAPI(title="Company CDR Human Curation", version="0.4-company-bootstrap")
    preview_root = (workspace.resolve() / "previews")

    @app.get("/curation", response_class=HTMLResponse)
    def page() -> str:
        return HTML

    @app.get("/api/v1/company-curation/next")
    def next_item() -> dict:
        rows = database.rows(
            "preview_status='COMPLETE' AND human_quality_status='UNREVIEWED'"
        )
        if not rows:
            return {"item": None, "progress": "complete"}
        row = rows[0]
        facts = {}
        if row.get("inspection_json"):
            import json
            facts = json.loads(row["inspection_json"])
        return {
            "item": {
                "file_id": row["file_id"],
                "filename": row["filename"],
                "dimensions": [facts.get("page_width"), facts.get("page_height")],
                "page_count": facts.get("page_count"),
                "object_count": facts.get("object_count"),
            },
            "progress": f"remaining {len(rows)}",
        }

    @app.get("/api/v1/company-curation/preview/{file_id}")
    def preview(file_id: str) -> FileResponse:
        try:
            row = database.get_file(file_id)
            candidate = Path(row["preview_path"] or "").resolve(strict=True)
            if preview_root != candidate and preview_root not in candidate.parents:
                raise PermissionError("preview outside workspace")
        except (KeyError, OSError, PermissionError) as exc:
            raise HTTPException(status_code=404, detail="preview not found") from exc
        return FileResponse(candidate, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/company-curation/submit")
    def submit(request: CurateRequest) -> dict:
        try:
            rights = (
                RightsStatus.CONFIRMED_COMPANY_OWNED
                if request.confirm_company_rights
                else RightsStatus.UNKNOWN
            )
            result = curate_file(
                database,
                file_id=request.file_id,
                reviewer=request.reviewer,
                quality=request.quality,
                category=request.category,
                gold_status=(
                    GoldStatus.HUMAN_CERTIFIED_GOLD
                    if request.certify_gold
                    else GoldStatus.GOLD_CANDIDATE
                    if request.quality == HumanQualityStatus.APPROVE
                    else GoldStatus.NOT_GOLD
                ),
                rights_status=rights,
                commercial_allowed=request.commercial_allowed,
                notes=request.notes,
                source="human_ui_action",
            )
        except (KeyError, ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"saved": True, "file_id": result.file_id, "gold_status": result.gold_status}

    return app
