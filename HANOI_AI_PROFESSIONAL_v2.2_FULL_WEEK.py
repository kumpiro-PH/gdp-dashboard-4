import os
import streamlit as st
import pandas as pd
from datetime import datetime
from collections import Counter, defaultdict
import base64
import requests
from io import StringIO

st.set_page_config(page_title="HANOI AI PROFESSIONAL v2.3", layout="wide")

MIN_HISTORY_FOR_DYNAMIC_WEIGHT = 5
RECENT_WINDOW = 30

DAY_CSV_FILES = {
    "Monday": "history_hanoi_mon.csv",
    "Tuesday": "history_hanoi_tue.csv",
    "Wednesday": "history_hanoi_wed.csv",
    "Thursday": "history_hanoi_thu.csv",
    "Friday": "history_hanoi_fri.csv",
    "Saturday": "history_hanoi_sat.csv",
    "Sunday": "history_hanoi_sun.csv"
}

DEFAULT_DAILY_NUMBERS = {
    "Monday": "459781",
    "Tuesday": "986304",
    "Wednesday": "698741",
    "Thursday": "421590",
    "Friday": "761438",
    "Saturday": "094572",
    "Sunday": "768304"
}

FORMULAS = [
    "Carry Over",
    "±1",
    "Sum Modulo",
    "Cross Sum",
    "Daily 6-Digit",
    "Rotation",
    "Mirror",
    "Shift +2",
    "Double",
    "Sandwich",
    "Position Weight",
    "Digit Transition",
    "Pair Relationship",
    "Hot-Cold Momentum",
    "Repeat & Echo",
    "First Prize Tail 2D",
]

def zfill_num(value, width):
    try:
        if pd.isna(value):
            return "0" * width
        s = str(value).strip()
        if "." in s:
            s = s.split(".")[0]
        return s.zfill(width)[-width:]
    except Exception:
        return "0" * width

def parse_thai_date(x):
    try:
        parts = str(x).strip().split("/")
        if len(parts) != 3:
            return pd.NaT
        day, month, year = map(int, parts)
        if year < 100:
            year += 2500
        if year >= 2400:
            year -= 543
        return pd.Timestamp(year=year, month=month, day=day)
    except Exception:
        return pd.NaT

def parse_date_for_sort(date_str):
    try:
        dt = parse_thai_date(date_str)
        if pd.notna(dt):
            return dt
    except Exception:
        pass
    return datetime(1900, 1, 1)

def get_csv_filename_for_day(day_en):
    return DAY_CSV_FILES.get(day_en, "history_hanoi_mon.csv")

# ==========================================
# GITHUB API SYNC FUNCTIONS (AUTO CREATE IF NOT EXISTS)
# ==========================================
@st.cache_data(ttl=600, show_spinner="กำลังโหลดข้อมูลจาก GitHub...")
def load_csv_data_from_github(day_en):
    csv_file = get_csv_filename_for_day(day_en)
    github_token = st.secrets.get("GITHUB_TOKEN")
    repo_name = st.secrets.get("GITHUB_REPO")
    
    if github_token and repo_name and csv_file:
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }
        file_url = f"https://api.github.com/repos/{repo_name}/contents/{csv_file}"
        try:
            res = requests.get(file_url, headers=headers)
            if res.status_code == 200:
                file_data = res.json()
                content_decoded = base64.b64decode(file_data["content"]).decode("utf-8-sig")
                df = pd.read_csv(StringIO(content_decoded), dtype=str).fillna("")
                df.columns = df.columns.str.strip().str.lstrip('|')
                return df
        except Exception:
            pass
            
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file, dtype=str, encoding="utf-8-sig").fillna("")
            df.columns = df.columns.str.strip().str.lstrip('|')
            return df
        except Exception:
            pass
            
    # Do not inject a fabricated draw: an empty history is safer than fake training data.
    return pd.DataFrame(columns=["date", "special", "first_prize", "top_3", "bottom_2"])

def save_history_to_github(day_en, new_row_df):
    csv_file = get_csv_filename_for_day(day_en)
    new_date = new_row_df.iloc[0]["date"]
    
    github_token = st.secrets.get("GITHUB_TOKEN")
    repo_name = st.secrets.get("GITHUB_REPO")
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    
    if not github_token or not repo_name:
        st.error("ยังไม่ได้ตั้งค่า GITHUB_TOKEN หรือ GITHUB_REPO ใน Streamlit Secrets")
        return False
        
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    file_url = f"https://api.github.com/repos/{repo_name}/contents/{csv_file}"
    
    res = requests.get(file_url, headers=headers)
    file_sha = None
    existing_df = pd.DataFrame(columns=["date", "special", "first_prize", "top_3", "bottom_2"])
    
    if res.status_code == 200:
        file_data = res.json()
        file_sha = file_data["sha"]
        content_decoded = base64.b64decode(file_data["content"]).decode("utf-8-sig")
        existing_df = pd.read_csv(StringIO(content_decoded), dtype=str).fillna("")
        existing_df.columns = existing_df.columns.str.strip().str.lstrip('|')
        
    if not existing_df.empty and "date" in existing_df.columns:
        existing_df = existing_df[existing_df["date"] != new_date]
        
    updated_df = pd.concat([new_row_df, existing_df], ignore_index=True)
    
    if "date" in updated_df.columns:
        updated_df["_temp_date"] = updated_df["date"].apply(parse_date_for_sort)
        updated_df = updated_df.sort_values(by="_temp_date", ascending=False, na_position="last")
        updated_df = updated_df.drop(columns=["_temp_date"])
        
    csv_string = updated_df.to_csv(index=False, encoding="utf-8-sig")
    encoded_content = base64.b64encode(csv_string.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": f"Create or Update {csv_file} for {new_date} via Streamlit App",
        "content": encoded_content,
        "branch": branch
    }
    if file_sha:
        payload["sha"] = file_sha
        
    put_res = requests.put(file_url, headers=headers, json=payload)
    if put_res.status_code in [200, 201]:
        st.cache_data.clear()
        return True
    else:
        st.error(f"❌ GitHub API Error ({put_res.status_code}): {put_res.text}")
        return False

def load_history(day_en):
    df = load_csv_data_from_github(day_en)
    required = ["date", "special", "first_prize", "top_3", "bottom_2"]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    df["dt"] = df["date"].apply(parse_thai_date)
    df = df.dropna(subset=["dt"]).copy()
    df["top_3"] = df["top_3"].apply(lambda x: zfill_num(x, 3))
    df["bottom_2"] = df["bottom_2"].apply(lambda x: zfill_num(x, 2))
    df["weekday_en"] = df["dt"].dt.day_name()
    return df.sort_values("dt", ascending=False).reset_index(drop=True)

def get_transformations(top_3_str, bottom_2_str="00"):
    t3 = zfill_num(top_3_str, 3)
    b2 = zfill_num(bottom_2_str, 2)
    a, b, c = [int(x) for x in t3]
    d, e = [int(x) for x in b2]

    digits = [a, b, c, d, e]
    carry = {str(x) for x in digits}
    pm1 = {str((x + delta) % 10) for x in digits for delta in (-1, 1)}

    sum_t3 = (a + b + c) % 10
    sum_b2 = (d + e) % 10
    sum_total = (sum_t3 + sum_b2) % 10
    sum_formulas = {str(sum_t3), str(sum_b2), str(sum_total)}

    cross_formulas = {
        str((b + e) % 10),
        str((c + d) % 10),
        str((a + d) % 10),
        str((a + e) % 10),
    }

    rotations = {t3[1:] + t3[0], t3[2] + t3[:2]}
    rotations_b2 = {b2[::-1]}
    mirror_map = {0: 5, 1: 6, 2: 7, 3: 8, 4: 9, 5: 0, 6: 1, 7: 2, 8: 3, 9: 4}
    mirror = "".join(str(mirror_map[int(x)]) for x in t3)
    mirror_b2 = "".join(str(mirror_map[int(x)]) for x in b2)
    shifted = "".join(str((int(x) + 2) % 10) for x in t3)
    shifted_b2 = "".join(str((int(x) + 2) % 10) for x in b2)
    doubles = {x * 2 for x in t3}
    sandwiches = {a_str + b_str + a_str for a_str in t3 for b_str in t3 if a_str != b_str}

    return {
        "carry_over": carry,
        "pm1": pm1,
        "sum_formulas": sum_formulas,
        "cross_formulas": cross_formulas,
        "rotations": rotations,
        "rotations_b2": rotations_b2,
        "mirror": mirror,
        "mirror_b2": mirror_b2,
        "shifted": shifted,
        "shifted_b2": shifted_b2,
        "doubles": doubles,
        "sandwiches": sandwiches,
    }

def daily_number_for_day(day, history=None):
    return DEFAULT_DAILY_NUMBERS.get(day, "000000")


def _recent_history(history, limit=30):
    """Return newest-first history; never use tail() for recent observations."""
    if history is None or history.empty:
        return pd.DataFrame()
    if "dt" in history.columns:
        return history.sort_values("dt", ascending=False).head(limit).reset_index(drop=True)
    return history.head(limit).reset_index(drop=True)


def formula_candidates(base_t3, base_b2, next_day, history=None):
    """Build candidate digits from the 10 original formulas + 5 adaptive engines."""
    trans = get_transformations(base_t3, base_b2)
    daily = daily_number_for_day(next_day, history)
    candidates = defaultdict(set)

    # Original 10 formulas: retained
    candidates["Carry Over"].update(trans["carry_over"])
    candidates["±1"].update(trans["pm1"])
    candidates["Sum Modulo"].update(trans["sum_formulas"])
    candidates["Cross Sum"].update(trans["cross_formulas"])
    candidates["Daily 6-Digit"].update(daily)
    candidates["Rotation"].update(set("".join(trans["rotations"])))
    candidates["Mirror"].update(trans["mirror"])
    candidates["Shift +2"].update(trans["shifted"])
    candidates["Double"].update(set("".join(trans["doubles"])))
    candidates["Sandwich"].update(set("".join(trans["sandwiches"])))

    hist = _recent_history(history, 30)
    current_top = zfill_num(base_t3, 3)
    current_bottom = zfill_num(base_b2, 2)

    # Focused 2D source: last two digits of the latest first-prize number.
    latest_row = _recent_history(history, 1)
    latest_first_prize_raw = str(latest_row.iloc[0].get("first_prize", "")).strip() if not latest_row.empty else ""
    latest_first_prize = zfill_num(latest_first_prize_raw, 5) if latest_first_prize_raw else ""
    first_prize_tail = latest_first_prize[-2:] if latest_first_prize else ""
    if first_prize_tail:
        candidates["First Prize Tail 2D"].update(first_prize_tail)

    # 11. Position Weight: recent frequency by position, separately for top/bottom.
    pos_top = Counter()
    pos_bottom = Counter()
    pos_top_by_position = [Counter() for _ in range(3)]
    pos_bottom_by_position = [Counter() for _ in range(2)]
    for rank, (_, row) in enumerate(hist.iterrows()):
        decay = 1.0 / (1.0 + rank * 0.10)
        t3 = zfill_num(row.get("top_3", "000"), 3)
        b2 = zfill_num(row.get("bottom_2", "00"), 2)
        for pos, digit in enumerate(t3):
            pos_top[digit] += decay * (1.20 if pos == 0 else 1.0)
        for pos, digit in enumerate(b2):
            pos_bottom[digit] += decay
    candidates["Position Weight"].update(d for d, _ in pos_top.most_common(5))
    candidates["Position Weight"].update(d for d, _ in pos_bottom.most_common(5))

    # 12. Digit Transition: learn per-position modulo transitions from adjacent draws.
    if len(hist) >= 2:
        for i in range(min(len(hist) - 1, 20)):
            newer, older = hist.iloc[i], hist.iloc[i + 1]
            nt = zfill_num(newer["top_3"], 3)
            ot = zfill_num(older["top_3"], 3)
            nb = zfill_num(newer["bottom_2"], 2)
            ob = zfill_num(older["bottom_2"], 2)
            for old_digit, new_digit in zip(ot + ob, nt + nb):
                delta = (int(new_digit) - int(old_digit)) % 10
                candidates["Digit Transition"].add(str((int(new_digit) + delta) % 10))
                candidates["Digit Transition"].add(str((int(new_digit) - delta) % 10))

    # 13. Pair Relationship: pair sums/differences from latest draw.
    base_digits = [int(x) for x in current_top + current_bottom]
    for i in range(len(base_digits)):
        for j in range(i + 1, len(base_digits)):
            candidates["Pair Relationship"].add(str((base_digits[i] + base_digits[j]) % 10))
            candidates["Pair Relationship"].add(str(abs(base_digits[i] - base_digits[j]) % 10))

    # 14. Hot-Cold Momentum: recent 10/20/30-draw frequency blend.
    if not hist.empty:
        momentum = Counter()
        for window, factor in ((10, 1.0), (20, 0.65), (30, 0.35)):
            part = hist.head(min(window, len(hist)))
            for _, row in part.iterrows():
                momentum.update({d: factor for d in (zfill_num(row["top_3"], 3) + zfill_num(row["bottom_2"], 2))})
        candidates["Hot-Cold Momentum"].update(d for d, _ in momentum.most_common(6))

    # 15. Repeat & Echo: repeat digits across latest draws, including positional echo.
    if len(hist) >= 2:
        latest_digits = current_top + current_bottom
        prior_digits = zfill_num(hist.iloc[1]["top_3"], 3) + zfill_num(hist.iloc[1]["bottom_2"], 2)
        candidates["Repeat & Echo"].update(set(latest_digits) & set(prior_digits))
        candidates["Repeat & Echo"].update(d for d in latest_digits if latest_digits.count(d) > 1)
    else:
        candidates["Repeat & Echo"].update(d for d in current_top + current_bottom if (current_top + current_bottom).count(d) > 1)

    # Attach position-frequency evidence for scoring and reporting.
    trans["position_top"] = pos_top
    trans["position_bottom"] = pos_bottom
    trans["position_top_by_position"] = pos_top_by_position
    trans["position_bottom_by_position"] = pos_bottom_by_position
    trans["first_prize"] = latest_first_prize
    trans["first_prize_tail"] = first_prize_tail
    trans["candidate_map"] = {name: set(candidates.get(name, set())) for name in FORMULAS}
    return candidates, daily, trans


def evaluate_formula(formula, trans, daily, actual_t3, actual_b2):
    """Digit-hit evaluation; 1 means at least one digit overlap, not exact prediction."""
    t3, b2 = zfill_num(actual_t3, 3), zfill_num(actual_b2, 2)
    if formula == "First Prize Tail 2D":
        tail = trans.get("first_prize_tail", "")
        return 0, int(bool(tail) and bool(set(b2) & set(tail)))
    if formula == "Rotation":
        return int(t3 in trans["rotations"]), int(b2 in trans["rotations_b2"])
    if formula == "Mirror":
        return int(t3 == trans["mirror"]), int(b2 == trans["mirror_b2"])
    if formula == "Shift +2":
        return int(t3 == trans["shifted"]), int(b2 == trans["shifted_b2"])
    if formula == "Double":
        double_digits = set("".join(trans["doubles"]))
        return int(any(d in t3 for d in double_digits)), int(any(d in b2 for d in double_digits))
    if formula == "Sandwich":
        return int(t3 in trans["sandwiches"]), 0
    digits = trans.get("candidate_map", {}).get(formula, set())
    return int(bool(set(t3) & set(digits))), int(bool(set(b2) & set(digits)))


def exact_pattern_score(formula, trans, daily, actual_t3, actual_b2):
    """Exact set/pattern score is kept separate from digit overlap."""
    t3, b2 = zfill_num(actual_t3, 3), zfill_num(actual_b2, 2)
    if formula == "First Prize Tail 2D":
        tail = trans.get("first_prize_tail", "")
        return 0.0, float(bool(tail) and b2 == tail)
    if formula == "Rotation":
        return float(t3 in trans["rotations"]), float(b2 in trans["rotations_b2"])
    if formula == "Mirror":
        return float(t3 == trans["mirror"]), float(b2 == trans["mirror_b2"])
    if formula == "Shift +2":
        return float(t3 == trans["shifted"]), float(b2 == trans["shifted_b2"])
    if formula == "Daily 6-Digit":
        daily_digits = set(daily)
        return float(set(t3).issubset(daily_digits)), float(set(b2).issubset(daily_digits))
    if formula == "Double":
        return float(any(t3[i] == t3[i + 1] for i in range(2))), float(b2[0] == b2[1])
    if formula == "Sandwich":
        return float(t3[0] == t3[2]), 0.0
    return 0.0, 0.0


def backtest_dataframe(df):
    """Walk-forward test in chronological order. Each prediction sees prior rows only."""
    if df is None or len(df) < 2:
        return pd.DataFrame()
    ordered = df.sort_values("dt", ascending=True).reset_index(drop=True) if "dt" in df.columns else df.reset_index(drop=True)
    rows = []
    for i in range(1, len(ordered)):
        history_prior = ordered.iloc[:i].sort_values("dt", ascending=False).reset_index(drop=True) if "dt" in ordered.columns else ordered.iloc[:i].iloc[::-1].reset_index(drop=True)
        prev = history_prior.iloc[0]
        actual = ordered.iloc[i]
        day = actual.get("weekday_en", "")
        candidates, daily, trans = formula_candidates(prev["top_3"], prev["bottom_2"], day, history_prior)
        for formula in FORMULAS:
            hit3, hit2 = evaluate_formula(formula, trans, daily, actual["top_3"], actual["bottom_2"])
            exact3, exact2 = exact_pattern_score(formula, trans, daily, actual["top_3"], actual["bottom_2"])
            rows.append({
                "date": actual.get("date", ""),
                "weekday": day,
                "formula": formula,
                "hit_3d": hit3,
                "hit_2d": hit2,
                "exact_3d": exact3,
                "exact_2d": exact2,
                "digit_overlap_3d": len(set(zfill_num(actual["top_3"], 3)) & candidates.get(formula, set())),
                "digit_overlap_2d": len(set(zfill_num(actual["bottom_2"], 2)) & candidates.get(formula, set())),
            })
    return pd.DataFrame(rows)


def formula_ranking(df):
    bt = backtest_dataframe(df)
    if bt.empty:
        return pd.DataFrame()
    result = []
    for formula in FORMULAS:
        x = bt[bt["formula"] == formula]
        n = len(x)
        if n == 0:
            continue
        hit3, hit2 = x["hit_3d"].mean(), x["hit_2d"].mean()
        avg_exact3, avg_exact2 = x["exact_3d"].mean(), x["exact_2d"].mean()
        composite = (0.35 * hit3 + 0.30 * hit2 + 0.20 * avg_exact3 + 0.15 * avg_exact2) * 100
        result.append({
            "Formula": formula, "N": n,
            "3D Digit-Hit%": round(hit3 * 100, 1),
            "2D Digit-Hit%": round(hit2 * 100, 1),
            "3D Full-Coverage%": round(avg_exact3 * 100, 1),
            "2D Full-Coverage%": round(avg_exact2 * 100, 1),
            "Composite": round(composite, 1),
        })
    return pd.DataFrame(result).sort_values("Composite", ascending=False).reset_index(drop=True)


def dynamic_weights(df):
    """Per-day weights shrunk toward neutral when sample size is small."""
    ranking = formula_ranking(df)
    if ranking.empty:
        return {f: 1.0 for f in FORMULAS}
    weights = {f: 1.0 for f in FORMULAS}
    for _, row in ranking.iterrows():
        sample_factor = min(1.0, float(row["N"]) / 30.0)
        raw = 0.65 + float(row["Composite"]) / 100.0
        weights[row["Formula"]] = max(0.70, min(1.55, 1.0 + (raw - 1.0) * sample_factor))
    return weights


def digit_scores(df, next_day):
    """Separate top/bottom scores; all history and formula weights are day-specific."""
    if df is None or df.empty:
        empty = {str(i): 0.0 for i in range(10)}
        return empty, {}, DEFAULT_DAILY_NUMBERS.get(next_day, "000000"), empty, empty, [Counter() for _ in range(5)]
    hist = _recent_history(df, max(100, len(df)))
    latest = hist.iloc[0]
    candidates, daily, trans = formula_candidates(latest["top_3"], latest["bottom_2"], next_day, hist)
    weights = dynamic_weights(hist)
    top_scores = {str(i): 0.0 for i in range(10)}
    bottom_scores = {str(i): 0.0 for i in range(10)}

    for formula in FORMULAS:
        w = weights.get(formula, 1.0)
        for digit in candidates.get(formula, set()):
            if formula == "First Prize Tail 2D":
                # First-prize ending contributes only to the 2D-lower model.
                bottom_scores[digit] += 1.50 * w
            else:
                top_scores[digit] += w
                bottom_scores[digit] += w

    # Position-specific frequency from latest 30 rows (not oldest rows).
    recent = hist.head(min(30, len(hist)))
    position_top = [Counter() for _ in range(3)]
    position_bottom = [Counter() for _ in range(2)]
    for rank, (_, row) in enumerate(recent.iterrows()):
        decay = 1.0 / (1.0 + rank * 0.08)
        t3, b2 = zfill_num(row["top_3"], 3), zfill_num(row["bottom_2"], 2)
        for pos, digit in enumerate(t3):
            contribution = decay * (1.20 if pos == 0 else 1.0)
            top_scores[digit] += contribution
            position_top[pos][digit] += contribution
        for pos, digit in enumerate(b2):
            bottom_scores[digit] += decay
            position_bottom[pos][digit] += decay
    # Daily number contributes once per distinct digit; avoid duplicate inflation.
    for digit in set(daily):
        top_scores[digit] += 0.75
        bottom_scores[digit] += 0.75

    # Composite display score; ranking engines retain their own top/bottom scores.
    scores = {d: (top_scores[d] + bottom_scores[d]) / 2.0 for d in top_scores}
    position_scores = position_top + position_bottom
    return scores, weights, daily, top_scores, bottom_scores, position_scores


def _ranked_permutations(digits, scores, length, limit, position_scores=None):
    from itertools import permutations
    pool = list(digits)
    items = []
    for seq in permutations(pool, length):
        if position_scores:
            value = sum(position_scores[pos].get(d, 0.0) for pos, d in enumerate(seq))
        else:
            value = sum(scores.get(d, 0.0) for d in seq)
        items.append(("".join(seq), value))
    items.sort(key=lambda x: (-x[1], x[0]))
    return [x[0] for x in items[:limit]]


def generate_prediction(df, next_day):
    if df is None or df.empty:
        return None
    latest = _recent_history(df, max(100, len(df))).iloc[0]
    scores, weights, daily, top_scores, bottom_scores, position_scores = digit_scores(df, next_day)
    ordered = sorted(scores, key=lambda d: (-scores[d], d))
    top_ordered = sorted(top_scores, key=lambda d: (-top_scores[d], d))
    bottom_ordered = sorted(bottom_scores, key=lambda d: (-bottom_scores[d], d))
    den, rong, kan = ordered[0], ordered[1:4], ordered[4:7]

    # Smart limited combinations; top and bottom are ranked independently.
    top5 = ordered[:5]
    top4 = top_ordered[:5]
    bottom5 = bottom_ordered[:5]
    pairs = _ranked_permutations(bottom5, bottom_scores, 2, 10, position_scores[3:5])
    first_prize_tail = zfill_num(latest.get("first_prize", ""), 5)[-2:]
    if str(latest.get("first_prize", "")).strip():
        # Prioritize exact first-prize ending, then its reverse, then model-ranked pairs.
        prioritized = [first_prize_tail, first_prize_tail[::-1]]
        pairs = prioritized + [
            pair for pair in pairs if pair not in prioritized
        ][:max(0, 10 - len(prioritized))]
    triples = _ranked_permutations(top_ordered[:5], top_scores, 3, 10, position_scores[:3])
    four_digits = _ranked_permutations(top4, top_scores, 4, 10, position_scores[:4])
    five_digits = _ranked_permutations(top5, scores, 5, 10, position_scores[:5])
    doubles = [d + d for d in top_ordered[:5]]
    sandwiches = [a + b + a for a in top_ordered[:5] for b in top_ordered[:5] if a != b][:10]

    return {
        "latest": latest, "daily": daily, "scores": scores, "ordered": ordered,
        "top_scores": top_scores, "bottom_scores": bottom_scores,
        "top_ordered": top_ordered, "bottom_ordered": bottom_ordered,
        "den": den, "rong": rong, "kan": kan, "pairs": pairs,
        "triples": triples, "four_digits": four_digits, "five_digits": five_digits,
        "doubles": doubles, "sandwiches": sandwiches, "weights": weights,
        "latest_first_prize": zfill_num(latest.get("first_prize", ""), 5),
        "first_prize_tail": first_prize_tail,
    }


def full_week_status():
    rows = []
    for day, filename in DAY_CSV_FILES.items():
        hist = load_history(day)
        latest = hist.iloc[0] if not hist.empty else None
        rows.append({
            "Day": day,
            "CSV": filename,
            "Draws": len(hist),
            "Latest Date": latest["date"] if latest is not None else "-",
            "Latest Top 3": latest["top_3"] if latest is not None else "-",
            "Latest Bottom 2": latest["bottom_2"] if latest is not None else "-",
            "Daily Number": DEFAULT_DAILY_NUMBERS[day],
            "Status": "Ready" if len(hist) >= 2 else "Need history",
        })
    return pd.DataFrame(rows)

# ==========================================
# 🔍 ฟังก์ชันเสริมวิเคราะห์ผลรางวัลล่าสุด
# ==========================================
def analyze_latest_result(special_str, top3_str, bottom2_str):
    """Return three ranked digits safely, even when CSV fields are blank or masked."""
    def clean_digits(value):
        if value is None or pd.isna(value):
            return ""
        return "".join(ch for ch in str(value).strip() if ch.isdigit())

    sp = clean_digits(special_str)
    t3 = clean_digits(top3_str)
    b2 = clean_digits(bottom2_str)

    if sp:
        sp = sp.zfill(5)[-5:]
    if t3:
        t3 = t3.zfill(3)[-3:]
    if b2:
        b2 = b2.zfill(2)[-2:]

    digit_counts = Counter(sp + t3 + b2)
    ranked = [digit for digit, _ in digit_counts.most_common(3)]
    while len(ranked) < 3:
        ranked.append("—")
    return ranked


# --- STREAMLIT UI ---
st.title("🇻🇳 HANOI AI PROFESSIONAL v2.3")
st.markdown("Adaptive Pattern Engine | 10 สูตรเดิม + 5 Adaptive Engines + First Prize Tail 2D | Full Week | GitHub Sync แยกไฟล์รายวัน")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 รีเฟรช / ดึงข้อมูลล่าสุด"):
    st.cache_data.clear()
    st.success("ล้างแคชและดึงข้อมูลใหม่สำเร็จ!")
    st.rerun()

menu = st.sidebar.selectbox("📌 เลือกเมนูการใช้งาน", [
    "1. ทำนายผลล่วงหน้า (Forward Prediction)",
    "2. อัปเดตผลรางวัล",
    "3. ตรวจสอบประวัติ (History)",
    "4. จัดอันดับสูตร / Backtest",
    "5. เลขประจำวัน (Daily Numbers)",
    "6. ทดสอบกรณี 08/11/2569 (926-90)",
    "7. Full Week Dashboard (Monday-Sunday)"
])

day_th_map = {
    "Monday": "วันจันทร์",
    "Tuesday": "วันอังคาร",
    "Wednesday": "วันพุธ",
    "Thursday": "วันพฤหัสบดี",
    "Friday": "วันศุกร์",
    "Saturday": "วันเสาร์",
    "Sunday": "วันอาทิตย์"
}

if "1." in menu:
    st.header("🎯 ทำนายผลล่วงหน้า (Forward Prediction)")
    selected_day_th = st.selectbox("เลือกวันสำหรับงวดถัดไป", list(day_th_map.values()))
    next_day = [k for k, v in day_th_map.items() if v == selected_day_th][0]

    df = load_history(next_day)

    if df.empty:
        st.warning(f"⚠️ ยังไม่มีข้อมูลในไฟล์ `{DAY_CSV_FILES[next_day]}` กรุณาเพิ่มข้อมูลงวดก่อนหน้าก่อน")
    else:
        latest = df.iloc[0]
        p = generate_prediction(df, next_day)

        st.info(f"📌 ข้อมูลฐานล่าสุด: งวดวันที่ **{latest['date']}** | รางวัลพิเศษ: **{latest['special']}** | 3 ตัวบน: **{latest['top_3']}** | 2 ตัวล่าง: **{latest['bottom_2']}**")
        
        # แสดงผลวิเคราะห์เสริมจากผลรางวัลงวดล่าสุด
        top_draw_digits = analyze_latest_result(latest['special'], latest['top_3'], latest['bottom_2'])
        st.write(
            f"🔍 **วิเคราะห์เจาะลึกจากงวดล่าสุด:** "
            f"เลขที่ออกซ้ำบ่อยสุดคือ `{top_draw_digits[0]}` "
            f"(รอง: `{top_draw_digits[1]}` - `{top_draw_digits[2]}`)"
        )
        if top_draw_digits[0] == "—":
            st.warning("ข้อมูลผลรางวัลล่าสุดไม่มีตัวเลขที่ใช้วิเคราะห์ได้ กรุณาตรวจสอบแถวล่าสุดใน CSV")
        
        st.write(f"🏆 **รางวัลที่ 1:** `{p['latest_first_prize']}` | **2 ตัวท้ายรางวัลที่ 1:** `{p['first_prize_tail']}`")
        st.info(f"🎯 First Prize Tail 2D: เพิ่มน้ำหนักเลข `{p['first_prize_tail']}` เฉพาะการจัดอันดับ 2 ตัวล่าง")
        st.write(f"📅 เลขประจำวัน (Daily 6-Digit) สำหรับ {selected_day_th}: `{p['daily']}`")
        st.write(f"🔝 Top digit ranking: `{', '.join(p['top_ordered'][:5])}`")
        st.write(f"🔻 Bottom digit ranking: `{', '.join(p['bottom_ordered'][:5])}`")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="🎯 เลขเด่น (Top Pick)", value=p["den"], delta=f"Score: {p['scores'][p['den']]:.2f}")
        with col2:
            st.metric(label="🥈 เลขรอง", value=" - ".join(p["rong"]))
        with col3:
            st.metric(label="🥉 เลขกัน", value=" - ".join(p["kan"]))

        st.subheader("💡 แนวทางตัวเลขจัดชุด")
        st.markdown(f"**5D Smart Permutation:** `{', '.join(p['five_digits'])}`")
        st.markdown(f"**4D Smart Permutation:** `{', '.join(p['four_digits'])}`")
        st.markdown(f"**3D Smart Permutation:** `{', '.join(p['triples'])}`")
        st.markdown(f"**2D เน้นไป-กลับ:** `{', '.join(p['pairs'])}`")
        st.markdown(f"**เบิ้ล:** `{', '.join(p['doubles'])}`")
        st.markdown(f"**หาม:** `{', '.join(p['sandwiches'])}`")

elif "2." in menu:
    st.header("📝 อัปเดตผลรางวัลหวยฮานอย (ซิงก์แยกไฟล์รายวันขึ้น GitHub)")
    selected_day_th_update = st.selectbox("เลือกวันของผลรางวัลที่ต้องการบันทึก", list(day_th_map.values()), key="update_day_select")
    target_day_en = [k for k, v in day_th_map.items() if v == selected_day_th_update][0]

    with st.form("update_form"):
        date_str = st.text_input("ใส่วันที่ (DD/MM/YYYY พ.ศ., เช่น 06/11/2569)")
        special = st.text_input("รางวัลพิเศษ (5 หลัก)")
        first_prize = st.text_input("รางวัลที่ 1 (5 หลัก)")
        top_3 = st.text_input("เลข 3 ตัวบน (3 หลัก)")
        bottom_2 = st.text_input("เลข 2 ตัวล่าง (2 หลัก)")
        submitted = st.form_submit_button(f"💾 บันทึกและซิงก์เข้า {DAY_CSV_FILES[target_day_en]}")

        if submitted:
            if not date_str or not top_3 or not bottom_2:
                st.error("⚠️ กรุณากรอกวันที่ 3 ตัวบน และ 2 ตัวล่างให้ครบถ้วน")
            else:
                new_row = pd.DataFrame([{
                    "date": date_str.strip(),
                    "special": special.strip(),
                    "first_prize": first_prize.strip(),
                    "top_3": zfill_num(top_3, 3),
                    "bottom_2": zfill_num(bottom_2, 2),
                }])
                
                success = save_history_to_github(target_day_en, new_row)
                if success:
                    target_file = DAY_CSV_FILES[target_day_en]
                    st.success(f"✅ บันทึกและซิงก์ข้อมูลลงไฟล์ `{target_file}` บน GitHub สำเร็จเรียบร้อยแล้ว!")
                    st.rerun()
                else:
                    st.error("❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับ GitHub API กรุณาตรวจสอบ GITHUB_TOKEN และ Secrets อีกครั้ง")

elif "3." in menu:
    st.header("📜 ประวัติผลรางวัลทั้งหมด (History)")
    selected_day_th_hist = st.selectbox("เลือกดูประวัติของวันในสัปดาห์", list(day_th_map.values()), key="hist_day")
    next_day_hist = [k for k, v in day_th_map.items() if v == selected_day_th_hist][0]
    
    df_hist = load_history(next_day_hist)
    
    st.write(f"จำนวนข้อมูลในไฟล์ **{DAY_CSV_FILES[next_day_hist]}** ทั้งหมด: **{len(df_hist)}** งวด")
    cols = ["date", "special", "first_prize", "top_3", "bottom_2", "weekday_en"]
    st.dataframe(df_hist[cols], use_container_width=True, hide_index=True)

elif "4." in menu:
    st.header("📈 การจัดอันดับสูตร / Backtest")
    selected_day_th_bt = st.selectbox("เลือกวันสำหรับรัน Backtest", list(day_th_map.values()), key="bt_day")
    next_day_bt = [k for k, v in day_th_map.items() if v == selected_day_th_bt][0]
    
    df_bt_data = load_history(next_day_bt)
    df_sorted = df_bt_data.sort_values("dt").reset_index(drop=True)
    
    if len(df_sorted) < 2:
        st.warning(f"⚠️ ข้อมูลในไฟล์ `{DAY_CSV_FILES[next_day_bt]}` ไม่เพียงพอ ต้องมีอย่างน้อย 2 งวด")
    else:
        ranking = formula_ranking(df_sorted)
        st.dataframe(ranking, use_container_width=True)

elif "5." in menu:
    st.header("📅 เลขประจำวัน (Daily Numbers)")
    daily_data = []
    for en, th in day_th_map.items():
        daily_data.append({
            "วัน": th, 
            "ไฟล์ CSV": DAY_CSV_FILES.get(en, ""),
            "Daily 6-Digit": DEFAULT_DAILY_NUMBERS.get(en, "")
        })
    st.dataframe(pd.DataFrame(daily_data), use_container_width=True, hide_index=True)

elif "6." in menu:
    st.header("🧪 ทดสอบกรณีผลฮานอยปกติ 08/11/2569")
    st.caption("ใช้ผล 926 บน / 90 ล่าง เป็นค่า Actual ที่ผู้ใช้ระบุ เพื่อทดสอบกลไกเท่านั้น ไม่ใช้เป็นข้อมูลฝึกก่อนการทำนายงวดเดียวกัน")
    test_day = "Sunday"
    test_date = pd.Timestamp(year=2026, month=11, day=8)
    actual_top3 = "926"
    actual_bottom2 = "90"
    df_test_all = load_history(test_day)
    # Strict no-look-ahead: only draws dated before 08/11/2569 may generate this test prediction.
    df_before = df_test_all[df_test_all["dt"] < test_date].copy().sort_values("dt", ascending=False).reset_index(drop=True)
    st.write(f"ผลจริงที่ใช้ทดสอบ: **3 ตัวบน {actual_top3} | 2 ตัวล่าง {actual_bottom2}**")
    if df_before.empty:
        st.warning("ไม่มีประวัติก่อนวันที่ทดสอบใน history_hanoi_sun.csv จึงยังคำนวณ Backtest กรณีนี้ไม่ได้")
    else:
        pred_test = generate_prediction(df_before, test_day)
        actual_digits_top = set(actual_top3)
        actual_digits_bottom = set(actual_bottom2)
        predicted_digits = set(pred_test["ordered"][:5])
        hit_top = len(predicted_digits & actual_digits_top)
        hit_bottom = len(predicted_digits & actual_digits_bottom)
        exact3 = actual_top3 in pred_test["triples"]
        exact2 = actual_bottom2 in pred_test["pairs"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("เลขเด่นก่อนงวด", pred_test["den"])
        c2.metric("เลขร่วม 3 ตัวบน", f"{hit_top}/3")
        c3.metric("เลขร่วม 2 ตัวล่าง", f"{hit_bottom}/2")
        c4.metric("ตรงชุด 3 ตัว", "ตรง" if exact3 else "ไม่ตรง")
        st.write(f"**เลขเด่น 5 ตัวก่อนงวด:** `{', '.join(pred_test['ordered'][:5])}`")
        st.write(f"**ชุด 3 ตัวที่ระบบสร้าง:** `{', '.join(pred_test['triples'][:12])}`")
        st.write(f"**ชุด 2 ตัวที่ระบบสร้าง:** `{', '.join(pred_test['pairs'])}`")
        st.write(f"**ตรวจชุด 2 ตัวล่าง 90:** {'ตรง' if exact2 else 'ไม่ตรง'}")
        st.info("การนับเลขร่วมเป็นเพียง Digit Hit ไม่ใช่การทำนายเลขเต็มตรงชุด ควรใช้ Backtest หลายงวดเพื่อประเมินความสามารถจริง")
        st.subheader("คะแนนรายตัวเลขก่อนงวดทดสอบ")
        score_df = pd.DataFrame([{"Digit": d, "Score": round(pred_test["scores"][d], 3)} for d in pred_test["ordered"]])
        st.dataframe(score_df, use_container_width=True, hide_index=True)
        st.subheader("น้ำหนักสูตรจากประวัติก่อนงวดทดสอบ")
        weight_df = pd.DataFrame([{"Formula / Engine": k, "Weight": round(v, 3)} for k, v in pred_test["weights"].items()]).sort_values("Weight", ascending=False)
        st.dataframe(weight_df, use_container_width=True, hide_index=True)



elif "7." in menu:
    st.header("📊 FULL WEEK ADAPTIVE DASHBOARD")
    st.caption("แต่ละวันใช้ CSV, Daily Number และ Adaptive Weight ของตัวเอง ไม่มีการปะปนข้อมูลข้ามวัน")
    week_df = full_week_status()
    st.dataframe(week_df, use_container_width=True, hide_index=True)
    st.subheader("📈 Formula Ranking แยกตามวัน")
    selected_week_day_th = st.selectbox("เลือกวันสำหรับดูอันดับสูตร", list(day_th_map.values()), key="week_ranking_day")
    selected_week_day = [k for k, v in day_th_map.items() if v == selected_week_day_th][0]
    selected_hist = load_history(selected_week_day)
    if len(selected_hist) >= 2:
        ranking = formula_ranking(selected_hist)
        st.dataframe(ranking, use_container_width=True, hide_index=True)
        st.caption("Digit-Hit% หมายถึงมีเลขร่วมอย่างน้อยหนึ่งหลัก ไม่ใช่การทำนายชุดเต็มตรงทุกหลัก")
    else:
        st.warning(f"ข้อมูล {DAY_CSV_FILES[selected_week_day]} ยังไม่เพียงพอสำหรับ Backtest")
    st.subheader("🔢 Daily Number เดิม (คงค่า)")
    st.dataframe(pd.DataFrame([
        {"Day": day, "Daily Number": number, "CSV": DAY_CSV_FILES[day]}
        for day, number in DEFAULT_DAILY_NUMBERS.items()
    ]), use_container_width=True, hide_index=True)
