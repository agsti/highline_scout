import type posthog from "posthog-js";

export function loadPosthog(): Promise<typeof posthog> {
  return import("posthog-js").then(({ default: client }) => client);
}
