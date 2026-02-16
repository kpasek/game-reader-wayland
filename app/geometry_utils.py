from typing import List, Tuple

def calculate_merged_area(rects: List[Tuple[int, int, int, int]], img_w: int, img_h: int, margin_pct: float = 0.00) -> Tuple[int, int, int, int]:
    """
    Calculates the union of multiple rectangles and adds a margin percentage.
    rects: List of (x, y, w, h)
    img_w, img_h: Dimensions of the image to clamp coordinates.
    margin_pct: Percentage of the union size to add as margin on each side (0.05 = 5%).
    
    Returns: (x, y, w, h) of the merged area.
    """
    if not rects:
        return (0, 0, 0, 0)

    # 1. Calculate Union
    # Defensive: ensure each rect has length >=4 and numeric values
    cleaned = []
    for i, r in enumerate(rects):
        try:
            x = int(r[0]); y = int(r[1]); w = int(r[2]); h = int(r[3])
        except Exception:
            print(f"[geometry_utils][WARN] invalid rect at index {i}: {r} (skipping)")
            continue
        cleaned.append((x, y, w, h))

    if not cleaned:
        return (0, 0, 0, 0)

    min_x = min(r[0] for r in cleaned)
    min_y = min(r[1] for r in cleaned)
    max_x = max(r[0] + r[2] for r in cleaned)
    max_y = max(r[1] + r[3] for r in cleaned)

    
    u_w = max_x - min_x
    u_h = max_y - min_y
    
    # 2. Calculate Margins
    # Use 5% of the union size
    raw_mx = int(u_w * margin_pct)
    raw_my = int(u_h * margin_pct)
    
    # Clamp margin to reasonable limits to avoid excessive expansion on large areas
    # Min 5px, Max 50px (or 5% whichever is smaller in practice, but capping at 50 helps)
    # Actually, if the area is 1920px wide, 5% is 100px. This might feel too big.
    # Let's cap max margin pixel size to 40px to affect user perception.
    mx = max(3, min(raw_mx, 50))
    my = max(3, min(raw_my, 50))
    
    # 3. Apply Margins and Clamp
    # Ideally: start = min_x - mx, end = max_x + mx
    final_x1 = max(0, min_x - mx)
    final_y1 = max(0, min_y - my)
    final_x2 = min(img_w, max_x + mx)
    final_y2 = min(img_h, max_y + my)
    
    # 4. Convert back to x, y, w, h
    final_w = max(0, final_x2 - final_x1)
    final_h = max(0, final_y2 - final_y1)


    return (int(final_x1), int(final_y1), int(final_w), int(final_h))
