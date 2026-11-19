/**
 * The UI kit (K4 contract §4 item 4; README.md beside this): every part a
 * kernel screen or a module's page is built from, on the theme's tokens.
 * "@/kernel" exports all of it; `IconName` comes with the slots' types.
 */
import "./kit.css";

export { Accordion } from "./Accordion";
export type { AccordionProps, SectionState } from "./Accordion";
export { Attention } from "./Attention";
export type { AttentionProps } from "./Attention";
export { Button, LinkButton, buttonClass } from "./Button";
export type { ButtonLook, ButtonProps, LinkButtonProps } from "./Button";
export { Card } from "./Card";
export type { CardProps } from "./Card";
export { Dialog } from "./Dialog";
export type { DialogProps } from "./Dialog";
export { EmptyState } from "./EmptyState";
export type { EmptyStateProps } from "./EmptyState";
export { ErrorBoundary } from "./ErrorBoundary";
export { Field, Input, Select, Switch, TextArea } from "./Field";
export type { FieldProps, SwitchProps } from "./Field";
export { Icon } from "./Icon";
export type { IconProps } from "./Icon";
export { ICON_NAMES } from "./icons";
export { LoadError, failureWords } from "./LoadError";
export type { LoadErrorProps } from "./LoadError";
export { Chip, Pill } from "./Pill";
export type { ChipProps, Tone } from "./Pill";
export { landOn, reveal } from "./place";
export { RouteFocus } from "./RouteFocus";
export { SaveBar } from "./SaveBar";
export type { SaveBarProps } from "./SaveBar";
export { SaveConflict, resolveConflict, settingsConflict } from "./SaveConflict";
export type { Choices, FieldConflict, SaveConflictProps, SettingsConflict } from "./SaveConflict";
export { ScrollMemory } from "./ScrollMemory";
export { SectionHistory } from "./SectionHistory";
export type { HistoryVersion, SectionHistoryProps } from "./SectionHistory";
export { Table } from "./Table";
export type { Column, TableProps } from "./Table";
export { Tabs } from "./Tabs";
export type { TabItem, TabsProps } from "./Tabs";
export { ToastProvider, useToast } from "./Toast";
export type { ToastNote, ToastTone } from "./Toast";
export { UnsavedDialog } from "./UnsavedDialog";
export type { UnsavedDialogProps } from "./UnsavedDialog";
export { useLeaveGuard, useUnsavedGuard } from "./unsaved";
export type { UnsavedGuard } from "./unsaved";
export { and, quoted, when } from "./words";
