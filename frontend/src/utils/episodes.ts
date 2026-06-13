import type { EpisodeMeta } from "@/types";

/**
 * Return episodes sorted for display.
 *
 * Sort key per entry is `order ?? episode`, so projects that predate the
 * `order` field (or entries that somehow lack it) fall back to the
 * episode-number ordering they had before. Stable: equal keys keep their
 * relative input order.
 */
export function sortEpisodesForDisplay<T extends Pick<EpisodeMeta, "episode" | "order">>(
  episodes: readonly T[],
): T[] {
  const indexed = episodes.map((episode, index) => ({ episode, index }));
  indexed.sort((a, b) => {
    const keyDiff = episodeDisplayKey(a.episode) - episodeDisplayKey(b.episode);
    if (keyDiff !== 0) return keyDiff;
    return a.index - b.index;
  });
  return indexed.map(({ episode }) => episode);
}

function episodeDisplayKey(episode: Pick<EpisodeMeta, "episode" | "order">): number {
  return episode.order ?? episode.episode;
}
