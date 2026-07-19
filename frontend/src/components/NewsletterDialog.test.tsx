import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { NewsletterDialog } from "./NewsletterDialog";

vi.mock("@/lib/analytics", () => ({ capture: vi.fn() }));
import { capture } from "@/lib/analytics";

function renderDialog(overrides: Partial<Parameters<typeof NewsletterDialog>[0]> = {}) {
  const props = {
    open: true,
    onClose: vi.fn(),
    onSubscribed: vi.fn(),
    onDismissForever: vi.fn(),
    ...overrides,
  };
  render(
    <I18nProvider>
      <NewsletterDialog {...props} />
    </I18nProvider>,
  );
  return props;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("NewsletterDialog", () => {
  it("subscribes, shows the confirm message, marks the flag without closing, and captures anonymously", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 201 }));
    const props = renderDialog();

    await userEvent.type(screen.getByRole("textbox"), "rigger@example.com");
    await userEvent.click(screen.getByRole("button", { name: /subscribe|subscriu|suscribir/i }));

    await waitFor(() =>
      expect(screen.getByText(/almost there|ja gairebé|ya casi/i)).toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledWith("/subscribe", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ email: "rigger@example.com" }),
    }));
    expect(capture).toHaveBeenCalledWith("newsletter_signup");
    expect(capture).not.toHaveBeenCalledWith("newsletter_signup", expect.anything());
    expect(props.onSubscribed).toHaveBeenCalledTimes(1);
    expect(props.onDismissForever).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });

  it("shows an error and keeps the form when the server fails", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 502 }));
    const props = renderDialog();

    await userEvent.type(screen.getByRole("textbox"), "a@b.com");
    await userEvent.click(screen.getByRole("button", { name: /subscribe|subscriu|suscribir/i }));

    await waitFor(() =>
      expect(screen.getByText(/couldn't subscribe|no s'ha pogut|no se pudo/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(props.onDismissForever).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });

  it("dismisses forever without subscribing on Don't show again", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const props = renderDialog();

    await userEvent.click(
      screen.getByRole("button", { name: /don't show|no ho tornis|no volver/i }),
    );

    expect(props.onDismissForever).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });
});
