import { useEffect, useState } from "react";
import { fetchPublishedNotSeen, type PublishedNotSeen } from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";

/**
 * Posts marked published here that the bridge has not seen on LinkedIn yet.
 *
 * Posts' table lists publications, and these have none: a post sent to
 * LinkedIn is marked published by the scheduler at its time and recorded as
 * a publication only when the bridge reads it there. Analytics' post table
 * listed them beside the LinkedIn posts, and when that table moved to Posts
 * they went onto no list (review round 2, B2 b). They are a short group of
 * their own, with the reason they carry no figures, and nothing at all is
 * drawn when there are none.
 */
export function PublishedNotYetSeen() {
  const [posts, setPosts] = useState<PublishedNotSeen[] | null>(null);
  const [failed, setFailed] = useState(false);
  // Read again when the studio answers after an outage.
  const back = useStudioBack();

  useEffect(() => {
    let live = true;
    fetchPublishedNotSeen()
      .then((answer) => {
        if (!live) return;
        setPosts(answer);
        setFailed(false);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [back]);

  if (failed) {
    return (
      <p className="studio-meta mt-6 text-[10px] leading-snug text-ink-muted">
        POSTS MARKED PUBLISHED HERE AND NOT YET SEEN ON LINKEDIN COULD NOT BE READ.
      </p>
    );
  }
  if (!posts || posts.length === 0) return null;

  return (
    <section aria-labelledby="posts-not-yet-seen" className="mt-6">
      <p id="posts-not-yet-seen" className="studio-label mb-1">
        Published here, not yet seen on LinkedIn
      </p>
      <p className="mb-2 max-w-[86ch] text-[12px] leading-snug text-ink-muted">
        These are marked published in the studio and the bridge has not read them on LinkedIn yet, so they have no
        figures and no people here. Once it reads one, from your posts page in the bridge browser, it is listed with
        your other posts.
      </p>
      <ul className="flex flex-col divide-y divide-edge border-y border-edge">
        {posts.map((post) => (
          <li key={post.id} className="flex items-baseline gap-4 py-2">
            <span className="studio-meta w-28 shrink-0 text-[10px] text-ink-muted">
              {formatLocalDay(post.published_at, "Date not recorded").toUpperCase()}
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px] text-ink-secondary">
              {post.excerpt || "Untitled post"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
