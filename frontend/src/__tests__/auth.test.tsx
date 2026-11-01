import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
import { AuthScreen } from "../components/AuthScreen";
import { Sidebar } from "../components/Sidebar";
import { initials, relativeTime } from "../settings";
import type { CodeSent, User } from "../types";

const user: User = { id: 1, email: "ana@example.com", name: "Ana Lopez", is_admin: false };
const sent = (purpose: "login" | "signup", extra: Partial<CodeSent> = {}): CodeSent => ({
  sent: true, email: "ana@example.com", purpose, delivery: "email", expires_in: 600, resend_after: 30, ...extra,
});

afterEach(() => vi.restoreAllMocks());

describe("AuthScreen", () => {
  it("says an unknown email isn't registered and offers sign-up with it", async () => {
    vi.spyOn(api, "loginStart").mockRejectedValue(
      new ApiError("ana@example.com isn't registered with ContentBlitz yet. Sign up to create an account.", 404, "not_registered"),
    );
    const signup = vi.spyOn(api, "signupStart").mockResolvedValue(sent("signup"));
    render(<AuthScreen onSignedIn={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("ContentBlitz, AI that");
    expect(screen.getByText("Log in or create an account")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("isn't registered");

    await userEvent.click(screen.getByRole("button", { name: "Sign up with this email" }));
    expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("ana@example.com"); // kept for sign-up
    await userEvent.type(screen.getByLabelText("Your name"), "Ana Lopez");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(signup).toHaveBeenCalledWith("ana@example.com", "Ana Lopez");
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(/Thanks, Ana/)).toBeInTheDocument();
  });

  it("verifies a pasted code automatically and signs in", async () => {
    vi.spyOn(api, "loginStart").mockResolvedValue(sent("login"));
    const verify = vi.spyOn(api, "verify").mockResolvedValue({ user });
    const onSignedIn = vi.fn();
    render(<AuthScreen onSignedIn={onSignedIn} />);
    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com{Enter}");
    const first = await screen.findByLabelText("Digit 1");
    first.focus();
    await userEvent.paste("123 456");
    await waitFor(() => expect(verify).toHaveBeenCalledWith("ana@example.com", "123456", "login"));
    expect(onSignedIn).toHaveBeenCalledWith(user);
  });

  it("shows a wrong-code message, clears the cells and throttles resends", async () => {
    vi.spyOn(api, "loginStart").mockResolvedValue(sent("login", { delivery: "console", dev_code: "999999" }));
    vi.spyOn(api, "verify").mockRejectedValue(new ApiError("That code isn't right. 4 attempts left.", 401, "wrong_code"));
    render(<AuthScreen onSignedIn={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com{Enter}");
    expect(await screen.findByRole("note")).toHaveTextContent("Development code: 999999");
    for (let i = 1; i <= 6; i++) await userEvent.type(screen.getByLabelText(`Digit ${i}`), String(i));
    expect(await screen.findByRole("alert")).toHaveTextContent("4 attempts left");
    expect(screen.getByLabelText("Digit 1")).toHaveValue("");
    expect(screen.getByRole("button", { name: /Send a new code in \d+s/ })).toBeDisabled();
  });

  it("points an existing account back to log in", async () => {
    vi.spyOn(api, "signupStart").mockRejectedValue(new ApiError("Already has an account", 409, "already_registered"));
    render(<AuthScreen onSignedIn={vi.fn()} initialMode="signup" />);
    await userEvent.type(screen.getByLabelText("Your name"), "Ana");
    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await userEvent.click(await screen.findByRole("button", { name: "Log in instead" }));
    expect(screen.getByText("Log in or create an account")).toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  const voice = { name: "ContentBlitz", tone: "clear", audience: "marketers", style_rules: [], banned_phrases: [], preferred_terms: {} };
  const base = {
    user,
    threads: [
      { thread_id: "a", title: "Hybrid work post", created_at: 0, updated_at: Date.now() / 1000 },
      { thread_id: "b", title: "", created_at: 0, updated_at: Date.now() / 1000 - 7200 },
    ],
    threadId: "a",
    voice,
    running: false,
    open: false,
    onSelectThread: vi.fn(),
    onDeleteThread: vi.fn(),
    onNewConversation: vi.fn(),
    onVoiceSaved: vi.fn(),
    onSignOut: vi.fn(),
    onOpenAdmin: vi.fn(),
    onClose: vi.fn(),
  };

  it("shows who is signed in, their conversations and a New conversation button, with no provider settings", async () => {
    render(<Sidebar {...base} />);
    expect(screen.getByText("Ana Lopez")).toBeInTheDocument();
    expect(screen.getByText("ana@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hybrid work post just now" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("2 h ago")).toBeInTheDocument();
    for (const gone of [/API keys/i, /Offline/i, /Providers and quality/i, /Usage since/i, /Admin dashboard/]) {
      expect(screen.queryByText(gone)).toBeNull();
    }
    await userEvent.click(screen.getByRole("button", { name: /New conversation$/ }));
    expect(base.onNewConversation).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /^New conversation 2 h ago/ }));
    expect(base.onSelectThread).toHaveBeenCalledWith("b");
    await userEvent.click(screen.getByRole("button", { name: 'Remove "Hybrid work post" from the list' }));
    expect(base.onDeleteThread).toHaveBeenCalledWith("a");
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(base.onSignOut).toHaveBeenCalled();
  });

  it("links admins to the dashboard", async () => {
    render(<Sidebar {...base} user={{ ...user, is_admin: true }} />);
    await userEvent.click(screen.getByRole("link", { name: "Admin dashboard" }));
    expect(base.onOpenAdmin).toHaveBeenCalled();
  });
});

describe("helpers", () => {
  it("formats initials and relative times", () => {
    expect(initials("Ana  Maria Lopez")).toBe("AL");
    expect(initials("cher")).toBe("C");
    const now = 1_700_000_000_000;
    expect(relativeTime(now / 1000 - 30, now)).toBe("just now");
    expect(relativeTime(now / 1000 - 300, now)).toBe("5 min ago");
    expect(relativeTime(now / 1000 - 90000, now)).toBe("yesterday");
  });
});
