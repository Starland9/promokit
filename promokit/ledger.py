"""Spend ledger (JSONL) + budget guard. Every paid API call is recorded BEFORE it is sent (status=pending)
and updated after (status=done/failed) so a crash never hides a charge."""
from __future__ import annotations
import json, time, uuid, pathlib

class BudgetExceeded(RuntimeError): pass
class ConfirmationRequired(RuntimeError): pass

class Ledger:
    def __init__(self, path: pathlib.Path, project: str):
        self.path = pathlib.Path(path); self.project = project
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists(): self.path.write_text("")
    def records(self, project: str | None = None):
        out = []
        for line in self.path.read_text().splitlines():
            if not line.strip(): continue
            r = json.loads(line)
            if project is None or r.get("project") == project: out.append(r)
        return out
    def spent(self, project: str | None = None, include_pending: bool = True) -> float:
        tot = 0.0
        for r in self.records(project):
            if r["status"] == "done" or (include_pending and r["status"] == "pending") or r["status"] == "failed":
                tot += float(r.get("actual_usd", r.get("est_usd", 0.0)))
        return round(tot, 4)
    def open(self, kind: str, detail: dict, est_usd: float) -> str:
        rid = uuid.uuid4().hex[:12]
        self._append({"id": rid, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "project": self.project, "kind": kind,
                      "detail": detail, "est_usd": round(est_usd, 4), "status": "pending"})
        return rid
    def close(self, rid: str, status: str, actual_usd: float | None = None, usage: dict | None = None):
        lines = self.path.read_text().splitlines(); out = []
        for line in lines:
            if not line.strip(): continue
            r = json.loads(line)
            if r["id"] == rid:
                r["status"] = status
                if actual_usd is not None: r["actual_usd"] = round(actual_usd, 4)
                if usage: r["usage"] = usage
            out.append(json.dumps(r, ensure_ascii=False))
        self.path.write_text("\n".join(out) + "\n")
    def _append(self, r: dict):
        with open(self.path, "a") as f: f.write(json.dumps(r, ensure_ascii=False) + "\n")

class BudgetGuard:
    """Refuses any paid call that would push the project over its cap, or that lacks explicit confirmation."""
    def __init__(self, ledger: Ledger, max_usd: float, per_call_max_usd: float, confirmed: bool):
        self.ledger = ledger; self.max_usd = float(max_usd); self.per_call_max = float(per_call_max_usd); self.confirmed = confirmed
    def check(self, est_usd: float, what: str):
        if not self.confirmed:
            raise ConfirmationRequired(f"{what} would cost ~${est_usd:.3f}. Re-run with --yes to spend (see `promokit plan`).")
        if est_usd > self.per_call_max:
            raise BudgetExceeded(f"{what}: single call ~${est_usd:.2f} exceeds per_call_max_usd={self.per_call_max:.2f}.")
        spent = self.ledger.spent(self.ledger.project)
        if spent + est_usd > self.max_usd:
            raise BudgetExceeded(f"{what}: ${spent:.3f} already spent + ~${est_usd:.3f} > budget.max_usd={self.max_usd:.2f}. Raise the cap in project.yaml if intended.")
    def status(self) -> str:
        spent = self.ledger.spent(self.ledger.project)
        return f"spent ${spent:.2f} / cap ${self.max_usd:.2f} (per call max ${self.per_call_max:.2f}) confirmed={self.confirmed}"
