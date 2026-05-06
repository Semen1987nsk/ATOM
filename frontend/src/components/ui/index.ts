/**
 * UI primitives — единый entry-point.
 *
 * Использование:
 *   import { Button, Card, Tile, Modal, StatTile, Input } from "@/components/ui";
 *
 * Дизайн-токены и стили живут в src/app/globals.css. Эти компоненты — тонкие
 * React-обёртки, которые делают разметку консистентной (a11y, loading state,
 * layout), но НЕ содержат своих стилей.
 */
export { Button } from "./Button";
export type { ButtonProps } from "./Button";

export { Card, CardHeader, CardTitle, CardSubtitle } from "./Card";
export type { CardProps } from "./Card";

export { Tile } from "./Tile";
export type { TileProps } from "./Tile";

export { Input } from "./Input";
export type { InputProps } from "./Input";

export { Modal } from "./Modal";
export type { ModalProps } from "./Modal";

export { StatTile } from "./StatTile";
export type { StatTileProps } from "./StatTile";
