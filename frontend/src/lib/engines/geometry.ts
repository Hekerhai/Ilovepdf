/**
 * Page geometry shared by the in-browser editor, form builder and form filler.
 * Mirrors backend/app/tools/overlay.py (visual_to_user, user_rect) so both engines put things in the same place.
 */

/** [a, b, c, d, e, f]: maps visual coordinates (bottom-left origin, as the reader sees the page) to user space. */
export type Matrix = [number, number, number, number, number, number];

export type Box = { x: number; y: number; width: number; height: number };

export function visualToUser(rotation: number, crop: Box): Matrix {
  const { x: x0, y: y0, width: w, height: h } = crop;
  switch (((rotation % 360) + 360) % 360) {
    case 90:
      return [0, 1, -1, 0, x0 + w, y0];
    case 180:
      return [-1, 0, 0, -1, x0 + w, y0 + h];
    case 270:
      return [0, -1, 1, 0, x0, y0 + h];
    default:
      return [1, 0, 0, 1, x0, y0];
  }
}

export function visualSize(rotation: number, crop: Box): [number, number] {
  const r = ((rotation % 360) + 360) % 360;
  return r === 90 || r === 270 ? [crop.height, crop.width] : [crop.width, crop.height];
}

export function apply(m: Matrix, X: number, Y: number): [number, number] {
  return [m[0] * X + m[2] * Y + m[4], m[1] * X + m[3] * Y + m[5]];
}

/** A box in fractions of the visual page (top-left origin, as on screen) as a user-space rectangle. */
export function userRect(rotation: number, crop: Box, f: Box): Box {
  const [vw, vh] = visualSize(rotation, crop);
  const m = visualToUser(rotation, crop);
  const [ax, ay] = apply(m, f.x * vw, vh - f.y * vh);
  const [bx, by] = apply(m, (f.x + f.width) * vw, vh - (f.y + f.height) * vh);
  return { x: Math.min(ax, bx), y: Math.min(ay, by), width: Math.abs(bx - ax), height: Math.abs(by - ay) };
}

/** True when pdf-lib's standard fonts (WinAnsi) can draw the text; otherwise the server, with Unicode fonts, must. */
export function isWinAnsi(text: string): boolean {
  // Latin-1 plus the extra characters WinAnsi maps into 0x80–0x9F.
  return /^[\u0000-ÿ€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]*$/.test(text);
}

/** The inverse of userRect: a user-space rectangle as fractions of the visual page (top-left origin). */
export function fractionBox(rotation: number, crop: Box, rect: Box): Box {
  const [vw, vh] = visualSize(rotation, crop);
  const [a, b, c, d, e, f] = visualToUser(rotation, crop);
  const det = a * d - b * c;
  const toVisual = (x: number, y: number): [number, number] => [(d * (x - e) - c * (y - f)) / det, (-b * (x - e) + a * (y - f)) / det];
  const [ax, ay] = toVisual(rect.x, rect.y);
  const [bx, by] = toVisual(rect.x + rect.width, rect.y + rect.height);
  const left = Math.min(ax, bx);
  const top = Math.max(ay, by);
  return { x: left / vw, y: 1 - top / vh, width: Math.abs(bx - ax) / vw, height: Math.abs(by - ay) / vh };
}
