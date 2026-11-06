import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
import { AuthScreen } from "../components/AuthScreen";
import { Rail } from "../components/Rail";
import { SidePanel } from "../components/Sidebar";
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

describe("Rail", () => {
  const props = {
    user,
    view: "chat" as const,
    counts: { research: 10 },
    voiceOpen: false,
    onSelect: vi.fn(),
    onToggleVoice: vi.fn(),
    onOpenAdmin: vi.fn(),
    onSignOut: vi.fn(),
  };

  it("offers Chat, Content, Research and Export as icons and marks the current page", async () => {
    render(<Rail {...props} />);
    expect(screen.getByRole("button", { name: "Chat" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "Content" }));
    expect(props.onSelect).toHaveBeenCalledWith("content");
    await userEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(props.onSelect).toHaveBeenCalledWith("research");
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(props.onSelect).toHaveBeenCalledWith("export");
    for (const gone of [/API keys/i, /Offline/i, /Providers and quality/i, /Usage since/i]) {
      expect(screen.queryByText(gone)).toBeNull();
    }
  });

  it("shows the user's initials and opens a menu with Sign out", async () => {
    render(<Rail {...props} />);
    const avatar = screen.getByRole("button", { name: "Account: Ana Lopez" });
    expect(avatar).toHaveTextContent("AL");
    expect(screen.queryByRole("menuitem", { name: "Sign out" })).toBeNull();
    await userEvent.click(avatar);
    expect(screen.getByRole("menu", { name: "Account" })).toHaveTextContent("ana@example.com");
    expect(screen.queryByRole("menuitem", { name: "Admin dashboard" })).toBeNull();
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(props.onSignOut).toHaveBeenCalled();
  });

  it("gives admins a dashboard link in the account menu", async () => {
    render(<Rail {...props} user={{ ...user, is_admin: true }} />);
    await userEvent.click(screen.getByRole("button", { name: "Account: Ana Lopez" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Admin dashboard" }));
    expect(props.onOpenAdmin).toHaveBeenCalled();
  });
});

describe("SidePanel", () => {
  const voice = { name: "ContentBlitz", tone: "clear", audience: "marketers", style_rules: [], banned_phrases: [], preferred_terms: {} };
  const base = {
    mode: "chats" as const,
    threads: [
      { thread_id: "a", title: "Hybrid work post", created_at: 0, updated_at: Date.now() / 1000 },
      { thread_id: "b", title: "", created_at: 0, updated_at: Date.now() / 1000 - 7200 },
    ],
    threadId: "a",
    voice,
    running: false,
    pinned: false,
    onSelectThread: vi.fn(),
    onDeleteThread: vi.fn(),
    onNewConversation: vi.fn(),
    onVoiceSaved: vi.fn(),
    onTogglePin: vi.fn(),
    onClose: vi.fn(),
  };

  it("lists, searches, opens and removes conversations", async () => {
    render(<SidePanel {...base} />);
    expect(screen.getByRole("button", { name: "Hybrid work post just now" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("2 h ago")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^New conversation 2 h ago/ }));
    expect(base.onSelectThread).toHaveBeenCalledWith("b");
    await userEvent.click(screen.getByRole("button", { name: 'Remove "Hybrid work post" from the list' }));
    expect(base.onDeleteThread).toHaveBeenCalledWith("a");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search conversations" }), "hybrid");
    expect(screen.queryByText("2 h ago")).toBeNull();
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText('No conversations match "zzz".')).toBeInTheDocument();
  });

  it("has an options menu to keep the panel visible or start a conversation", async () => {
    render(<SidePanel {...base} />);
    await userEvent.click(screen.getByRole("button", { name: "Conversation options" }));
    const keep = screen.getByRole("menuitemcheckbox", { name: "Keep chat panel visible" });
    expect(keep).toHaveAttribute("aria-checked", "false");
    await userEvent.click(keep);
    expect(base.onTogglePin).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Conversation options" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "New conversation" }));
    expect(base.onNewConversation).toHaveBeenCalled();
  });

  it("invites the first conversation when there are none", () => {
    render(<SidePanel {...base} threads={[]} />);
    expect(screen.getByRole("heading", { name: "Start a conversation" })).toBeInTheDocument();
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
