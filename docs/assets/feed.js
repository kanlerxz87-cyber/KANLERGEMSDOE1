(function () {
  const target = document.getElementById("leaderboard-feed");
  if (!target) return;
  fetch("feed.json", { cache: "no-store" }).then(function (response) {
    if (!response.ok) throw new Error("feed unavailable");
    return response.json();
  }).then(function (data) {
    const stamp = typeof data.observed_utc === "string" ? data.observed_utc : "unknown date";
    const isFresh = data.status === "refreshed";
    target.textContent = isFresh
      ? "Public leaderboard snapshot refreshed on " + stamp + ". Open the official leaderboard for rank and score details; this is not a receipt for a repository raster."
      : "Stale public leaderboard snapshot observed on " + stamp + ". Open the official leaderboard for live values; this is not a receipt for a repository raster.";
  }).catch(function () {
    target.textContent = "Feed unavailable. Open the official leaderboard for live values. No repository submission receipt is recorded here.";
  });
}());
