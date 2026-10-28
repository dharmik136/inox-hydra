import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchIngressSettings, saveIngressSettings, type IngressSettings } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Your phone, through Telegram.
 *
 * The one way a phone reaches the studio: a bot the creator made, which the
 * studio asks for messages. Text becomes a draft; a LinkedIn post link
 * becomes the page Today asks them to open at this computer. The phone sends
 * a link, never a figure. The token is sealed like the AI key and never read
 * back; every line here is read from the server's own answer.
 *
 * Telegram never shows a creator their chat id, so the token can be saved
 * alone: every message is then refused, and the chats that wrote are listed
 * with the start of their first message and "Is that you?". This is me saves
 * that chat id through the same save, with the same shape check. Nothing
 * pairs a chat but that press.
 *
 * The sentence saying the bot has not been seen working on this computer
 * comes from the server too, and goes once a message from the saved chat has
 * been saved here.
 */
export function TelegramIngressPanel() {
  const [state, setState] = useState<IngressSettings | null>(null);
  const [token, setToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchIngressSettings()
      .then((result) => live && setState(result))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  // While the bot waits to be paired, the chat that writes to it shows up
  // here within a few seconds, without a reload.
  const pairing = !!state?.pairing && state.running;
  useEffect(() => {
    if (!pairing) return undefined;
    const timer = window.setInterval(() => {
      fetchIngressSettings()
        .then((result) => setState(result))
        .catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [pairing]);

  async function save(nextToken: string, nextChat: string, said: string) {
    setBusy(true);
    setNote(null);
    try {
      const result = await saveIngressSettings(nextToken, nextChat);
      setState(result);
      setToken("");
      setChatId("");
      setNote(said);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The save was refused.");
    } finally {
      setBusy(false);
    }
  }

  const rows: { label: string; value: string; good: boolean }[] = state
    ? [
        { label: "Bot token", value: state.has_token ? "SET, SEALED" : "NOT SET", good: state.has_token },
        { label: "Your chat id", value: state.chat_id || (state.pairing ? "NOT SET YET, PAIR BELOW" : "NOT SET"), good: !!state.chat_id },
        { label: "Asking Telegram for messages", value: state.running ? "YES" : "NO", good: state.running },
        // The count is the running bot's, so it is shown only for this profile's.
        ...(state.running
          ? [{ label: "Messages saved since the studio started", value: state.total_messages_processed.toLocaleString(), good: true }]
          : []),
        { label: "Posts asked for from the phone, waiting", value: state.open_requests.toLocaleString(), good: true },
      ]
    : [];

  return (
    <section className="mt-8 border-t border-edge pt-5">
      <p className="studio-label mb-2">Your phone, through Telegram</p>

      <p className="text-[13px] leading-relaxed text-ink-secondary">
        Make a Telegram bot of your own and the studio asks it for the messages you send. A LinkedIn post link
        becomes the page Today asks you to open at this computer; text becomes a draft. The phone sends a link,
        never a figure: the extension reads the real page here.
      </p>

      {state === null ? (
        <p className="studio-meta mt-3 text-ink-muted">READING</p>
      ) : (
        <>
          <dl className="mt-3 flex flex-col gap-1.5">
            {rows.map((row) => (
              <div key={row.label} className="flex items-baseline justify-between gap-4">
                <dt className="text-[12px] text-ink-secondary">{row.label}</dt>
                <dd className={cn("studio-meta", row.good ? "text-signal-green-text" : "text-ink-muted")}>{row.value}</dd>
              </div>
            ))}
            {state.running && state.last_error && (
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-[12px] text-ink-secondary">Last problem reaching Telegram</dt>
                <dd className="studio-meta text-signal-orange-text">{state.last_error}</dd>
              </div>
            )}
          </dl>
          {state.running && state.configured_from === "settings" && (
            <p className="mt-2 text-[12px] leading-relaxed text-ink-secondary">
              Messages to this bot are saved in this profile, whichever profile is open.
            </p>
          )}
          {state.running_for_another_profile && (
            <p className="mt-2 text-[12px] leading-relaxed text-ink-secondary">
              The studio is asking Telegram for the bot set up in another profile, and saves its messages
              there. One bot is asked at a time: saving one here switches to it.
            </p>
          )}
          {state.pairing && (
            <p className="mt-3 text-[12px] leading-relaxed text-ink-secondary">
              Now message your bot once from your phone. Your chat appears here with the start of your message:
              press This is me. That first message only says which chat is yours; it is not saved.
            </p>
          )}
          {state.refused_chats.length > 0 && (
            <div className="mt-3">
              <p className="studio-meta text-ink-muted">CHATS THE BOT REFUSED, NEWEST FIRST</p>
              <ul className="mt-1 flex flex-col gap-2">
                {state.refused_chats.map((chat) => (
                  <li key={chat.chat_id} className="flex flex-col items-start gap-1 text-[12px] leading-snug">
                    <span className="text-ink-secondary">
                      {`${chat.count.toLocaleString()} ${chat.count === 1 ? "message" : "messages"} refused from chat ${chat.chat_id}, first: '${chat.first}'.`}{" "}
                      {chat.own_chat
                        ? "Is that you?"
                        : "This is a group's chat: the studio takes messages only from your own chat with the bot."}
                    </span>
                    {chat.own_chat && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void save(
                            "",
                            chat.chat_id,
                            "Paired. Messages from this chat now arrive in the studio. The one you sent to pair was not kept, so send it again if you want it.",
                          )
                        }
                        className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                      >
                        This is me
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {state.recent_links.length > 0 && (
            <div className="mt-3">
              <p className="studio-meta text-ink-muted">LINKS FROM YOUR PHONE, NEWEST FIRST</p>
              <ul className="mt-1 flex flex-col gap-1.5">
                {state.recent_links.map((link) => (
                  <li key={link.id} className="text-[12px] leading-snug">
                    <span className="studio-meta block truncate text-ink-secondary">{link.activity_urn || link.link}</span>
                    <span className={link.state === "refused" ? "text-signal-orange-text" : "text-ink-secondary"}>
                      {link.said}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div className="mt-3 flex flex-col gap-2">
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Bot token"
          aria-label="Telegram bot token"
          className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
        />
        <input
          type="text"
          value={chatId}
          onChange={(event) => setChatId(event.target.value)}
          placeholder="Your numeric chat id, or leave empty and pair below"
          aria-label="Telegram chat id"
          className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() =>
              void save(
                token.trim(),
                chatId.trim(),
                chatId.trim() || state?.chat_id
                  ? "Saved. The studio is asking Telegram for your messages."
                  : "Saved. Now message your bot once from your phone, then press This is me beside your chat.",
              )
            }
            disabled={busy || !(token.trim() || (state?.has_token && chatId.trim()))}
            className="flex items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
            Save and start
          </button>
          {state?.has_token && (
            <button
              type="button"
              onClick={() => void save("", "", "Removed from this profile.")}
              disabled={busy}
              className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              Remove the bot
            </button>
          )}
        </div>

        {note && (
          <p role="status" className="studio-meta text-ink-secondary">
            {note}
          </p>
        )}

        {state?.not_yet_tested && (
          <p className="studio-meta leading-relaxed text-signal-orange-text">{state.not_yet_tested.toUpperCase()}</p>
        )}
        <p className="studio-meta leading-relaxed text-ink-muted">
          THE TOKEN IS SEALED IN THIS MACHINE&apos;S VAULT, LIKE YOUR AI KEY, AND NEVER SHOWN AGAIN. YOUR MESSAGES
          PASS THROUGH TELEGRAM&apos;S SERVERS. THE STUDIO ASKS TELEGRAM FOR THEM AND OPENS NO PORT; EACH REQUEST
          IS COUNTED UNDER INGRESS ABOVE.
        </p>
      </div>
    </section>
  );
}
