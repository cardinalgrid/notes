"""Write story.md, the plain-language version of Note 2, from results/summary.json and story.template.md."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RES = HERE / "results"


def main() -> int:
    s = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
    d = s["distinctness_median_index"]
    se, ro, rp, hy = s["seasonal"], s["regime_oracle_vs_g3"], s["regime_prevday_vs_g3"], s["hybrid_offset"]
    worst = pd.read_csv(RES / "r2a1_vs_g3_w2.csv").sort_values("gain_rel_pct").query("ci_hi < 0")["ba"].tolist()
    vals = {
        "n_bas": s["bas_eligible"],
        "ba_days": f"{s['ba_days']:,}",
        "g7_loss": f"{-s['g7_vs_g3']['mean_gain_rel_pct']:.0f}%",
        "idx_tue_wed": f"{d['Tue-Wed']:.2f}",
        "idx_mon_thu": f"{d['Mon-Thu']:.2f}",
        "hyb_mon": f"{hy['vs_G3_w3']['gain_by_weekday_pp']['Mon']:.2f}",
        "hyb_fri": f"{hy['vs_G3_w3']['gain_by_weekday_pp']['Fri']:.2f}",
        "s4_loss": f"{-se['S4_vs_G3_w2']['mean_gain_rel_pct']:.0f}%",
        "r2a1_up": se["R2A1_vs_G3_w2"]["bas_ci_above_zero"],
        "analog_worst_short": ", ".join(worst),
        "regime_top_gain": f"{ro['top'][0]['gain_rel_pct']:.0f}%",
        "regime_oracle": f"{ro['mean_gain_rel_pct']:.0f}%",
        "regime_prev": f"{rp['mean_gain_rel_pct']:.0f}%",
        "generated": s["generated"][:10],
        "t_heat": f"{s['temperature']['t_heat_f']:.0f} °F ({s['temperature']['t_heat_c']:.0f} °C)",
        "t_cool": f"{s['temperature']['t_cool_f']:.0f} °F ({s['temperature']['t_cool_c']:.0f} °C)",
        "g3t3_gain": f"{s['temperature']['G3T3_vs_G3']['mean_gain_rel_pct']:.0f}%",
        "best_gain": f"{s['temperature']['best_config']['BEST_vs_G3_w2']['mean_gain_rel_pct']:.0f}%",
    }
    text = (HERE / "story.template.md").read_text(encoding="utf-8")
    for k, v in vals.items():
        text = text.replace("{" + k + "}", str(v))
    assert "{" not in text.replace("{{", ""), "unfilled placeholder"
    (HERE / "story.md").write_text(text, encoding="utf-8", newline=chr(10))
    print("story.md written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
