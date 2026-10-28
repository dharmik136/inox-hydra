import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  fetchIngressSettings,
  saveIngressOptions,
  saveIngressSettings,
  sendIngressTestMessage,
  type IngressOptions,
  type IngressSettings,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** The whole hours quiet hours and the weekly summary can be set to. */
const HOURS = Array.from({ length: 24 }, (_unused, hour) => hour);

/** The weekly summary's days, as the server numbers them: 0 is Monday. */
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** A whole hour as the computer's clock shows it: 7 is 07:00. */
function clock(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

const SELECT = "rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary disabled:opacity-40";

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
 *
 * The bot answers (2.11.0): each message gets a short fixed sentence back,
 * which says what became of it and carries none of the creator's words or
 * figures. On by default; its switch is here. Phase 2: some messages carry
 * buttons, pressed on the phone (Undo, Remind me in an hour, Done), which the
 * descriptions below name.
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

  async function sendTest() {
    setBusy(true);
    setNote(null);
    try {
      const answer = await sendIngressTestMessage();
      setNote(answer.said);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The test message was not sent.");
    } finally {
      setBusy(false);
    }
  }

  async function setOption(change: Partial<IngressOptions>, said: string) {
    setBusy(true);
    setNote(null);
    try {
      setState(await saveIngressOptions(change));
      setNote(said);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The switch was not saved.");
    } finally {
      setBusy(false);
    }
  }

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
            {state.last_send_error && (
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-[12px] text-ink-secondary">Last message the bot could not send</dt>
                <dd className="studio-meta text-signal-orange-text">{state.last_send_error}</dd>
              </div>
            )}
          </dl>
          {state.has_token && (
            <div className="mt-3 flex flex-col gap-2">
              <p className="studio-meta text-ink-muted">WHAT THE BOT SAYS BACK</p>
              <OptionRow
                label="The bot confirms each message"
                detail="A short fixed sentence back, such as Saved as a draft in your studio, or Today will ask you to open this post's analytics. Never your words, never your figures. Under a saved draft, Undo removes it while you have not changed it here."
                checked={state.options.replies}
                disabled={busy}
                onChange={(on) => void setOption({ replies: on }, on ? "The bot confirms each message." : "The bot no longer confirms messages.")}
              />
              <OptionRow
                label="The bot may answer with your figures"
                detail="When on, /today answers with your latest post's figures, how many replies are waiting and when your next post is scheduled. Those figures then sit on Telegram's servers, as everything in the chat does. Never anyone else's name or comment."
                checked={state.options.figures}
                disabled={busy}
                onChange={(on) => void setOption({ figures: on }, on ? "The bot may answer /today with your figures." : "Your figures stay in the studio.")}
              />
              <p className="studio-meta mt-1 text-ink-muted">WHAT THE BOT TELLS YOU, EACH ONLY IF TICKED</p>
              <OptionRow
                label="Tell me when a queued post is due"
                detail="One message when a post in your queue is due: how many, never its words. Under it, Remind me in an hour, and Done, which only clears the reminder: nothing is marked as posted."
                checked={state.options.notify_due}
                disabled={busy}
                onChange={(on) => void setOption({ notify_due: on }, on ? "The bot tells you when a queued post is due." : "No message when a post is due.")}
              />
              <OptionRow
                label="Send my latest post's figures at about 24 hours"
                detail="Once, when the studio has read your latest post at about a day old: its impressions, reactions and comments, which then sit on Telegram's servers."
                checked={state.options.notify_24h}
                disabled={busy}
                onChange={(on) => void setOption({ notify_24h: on }, on ? "The bot sends your latest post's figures at about 24 hours." : "No message at 24 hours.")}
              />
              <OptionRow
                label="Send me a weekly summary"
                detail="Once a week: how many posts you published, drafts saved from your phone and replies waiting, and when your next post is scheduled. Your figures too, each with where and when it was read, only while the figures switch above is on. Never anyone's name or words."
                checked={state.options.weekly}
                disabled={busy}
                onChange={(on) =>
                  void setOption(
                    { weekly: on },
                    on
                      ? `A weekly summary on ${DAYS[state.options.weekly_day]} at ${clock(state.options.weekly_hour)}.`
                      : "No weekly summary.",
                  )
                }
              />
              <div className="flex flex-wrap items-center gap-2 pl-5 text-[12px] text-ink-secondary">
                <span>On</span>
                <select
                  aria-label="Weekly summary day"
                  className={SELECT}
                  value={state.options.weekly_day}
                  disabled={busy || !state.options.weekly}
                  onChange={(event) => {
                    const day = Number(event.target.value);
                    void setOption({ weekly_day: day }, `A weekly summary on ${DAYS[day]} at ${clock(state.options.weekly_hour)}.`);
                  }}
                >
                  {DAYS.map((name, index) => (
                    <option key={name} value={index}>
                      {name}
                    </option>
                  ))}
                </select>
                <span>at</span>
                <select
                  aria-label="Weekly summary hour"
                  className={SELECT}
                  value={state.options.weekly_hour}
                  disabled={busy || !state.options.weekly}
                  onChange={(event) => {
                    const hour = Number(event.target.value);
                    void setOption({ weekly_hour: hour }, `A weekly summary on ${DAYS[state.options.weekly_day]} at ${clock(hour)}.`);
                  }}
                >
                  {HOURS.map((hour) => (
                    <option key={hour} value={hour}>
                      {clock(hour)}
                    </option>
                  ))}
                </select>
                <span>on this computer&apos;s clock</span>
              </div>
              {state.weekly_next && (
                <p className="studio-meta pl-5 text-ink-muted">{`NEXT SUMMARY: ${state.weekly_next.toUpperCase()}`}</p>
              )}
              <p className="studio-meta mt-1 text-ink-muted">QUIET HOURS</p>
              <OptionRow
                label="Hold notifications during quiet hours"
                detail="The notifications above wait while it is quiet, and go when quiet hours end, each once. Answers to your own messages and presses are never held."
                checked={state.options.quiet_hours}
                disabled={busy}
                onChange={(on) =>
                  void setOption(
                    { quiet_hours: on },
                    on
                      ? `Quiet hours: ${clock(state.options.quiet_from)} to ${clock(state.options.quiet_to)}.`
                      : "Notifications go at any hour.",
                  )
                }
              />
              <div className="flex flex-wrap items-center gap-2 pl-5 text-[12px] text-ink-secondary">
                <span>From</span>
                <select
                  aria-label="Quiet hours start"
                  className={SELECT}
                  value={state.options.quiet_from}
                  disabled={busy || !state.options.quiet_hours}
                  onChange={(event) => {
                    const from = Number(event.target.value);
                    void setOption({ quiet_from: from }, `Quiet hours: ${clock(from)} to ${clock(state.options.quiet_to)}.`);
                  }}
                >
                  {HOURS.map((hour) => (
                    <option key={hour} value={hour}>
                      {clock(hour)}
                    </option>
                  ))}
                </select>
                <span>to</span>
                <select
                  aria-label="Quiet hours end"
                  className={SELECT}
                  value={state.options.quiet_to}
                  disabled={busy || !state.options.quiet_hours}
                  onChange={(event) => {
                    const to = Number(event.target.value);
                    void setOption({ quiet_to: to }, `Quiet hours: ${clock(state.options.quiet_from)} to ${clock(to)}.`);
                  }}
                >
                  {HOURS.map((hour) => (
                    <option key={hour} value={hour}>
                      {clock(hour)}
                    </option>
                  ))}
                </select>
                <span>on this computer&apos;s clock</span>
              </div>
              {state.quiet_now && (
                <p className="studio-meta pl-5 text-ink-muted">
                  {`QUIET NOW: NOTIFICATIONS WAIT UNTIL ${clock(state.options.quiet_to)}`}
                </p>
              )}
            </div>
          )}
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
          {state?.configured && (
            <button
              type="button"
              onClick={() => void sendTest()}
              disabled={busy}
              className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              Send a test message
            </button>
          )}
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

/** One of the bot's switches: a labelled checkbox with what it means beneath. */
function OptionRow({
  label,
  detail,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  detail: string;
  checked: boolean;
  disabled: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2 text-[12px] leading-relaxed">
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="min-w-0">
        <span className="text-ink-primary">{label}</span>
        <span className="block text-ink-secondary">{detail}</span>
      </span>
    </label>
  );
}
