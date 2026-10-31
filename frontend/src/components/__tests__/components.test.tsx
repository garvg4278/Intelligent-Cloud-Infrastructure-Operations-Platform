import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "../ConfirmDialog";
import { CopyButton } from "../CopyButton";
import { DataTable } from "../DataTable";
import { StatusBadge } from "../StatusBadge";

function Harness({ onConfirm = vi.fn() }: { onConfirm?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <ConfirmDialog open={open} title="Destroy it?" confirmLabel="Destroy" tone="danger" onConfirm={onConfirm} onCancel={() => setOpen(false)}>
        <p>Cannot be undone.</p>
      </ConfirmDialog>
    </>
  );
}

describe("ConfirmDialog", () => {
  it("is an accessible modal, focuses Cancel first, and Enter does not confirm by accident", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<Harness onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    const dialog = screen.getByRole("alertdialog", { name: "Destroy it?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("Cannot be undone.");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("traps Tab, closes on Escape and returns focus to the opener", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);
    await user.tab();
    expect(screen.getByRole("button", { name: "Destroy" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus(); // wrapped, did not escape to the page
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe("CopyButton", () => {
  it("copies and announces it", async () => {
    const user = userEvent.setup(); // installs a clipboard stub on navigator
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    render(<CopyButton text="ops@example.com" label="Copy support email" />);
    await user.click(screen.getByRole("button", { name: "Copy support email" }));
    expect(writeText).toHaveBeenCalledWith("ops@example.com");
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  it("renders a real table and labels each cell with its header for the stacked mobile layout", () => {
    render(<DataTable caption="Things" rows={[{ id: "1", name: "alpha" }]} rowKey={(r) => r.id} columns={[{ header: "Name", cell: (r) => r.name }]} />);
    const table = screen.getByRole("table", { name: "Things" });
    expect(within(table).getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(within(table).getByText("alpha")).toHaveAttribute("data-label", "Name");
  });
});

describe("StatusBadge", () => {
  it("styles every value the API can emit (the old UI missed `ready` and `firing`)", () => {
    for (const [value, tone] of [["ready", "good"], ["firing", "bad"], ["provision_failed", "bad"], ["investigating", "warn"], ["destroyed", "neutral"]] as const) {
      const { unmount } = render(<StatusBadge value={value} />);
      expect(screen.getByText(value.replace(/_/g, " "))).toHaveClass(`badge-${tone}`);
      unmount();
    }
  });
});
