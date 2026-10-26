(function () {
  const target = document.getElementById("leaderboard-feed");
  if (!target) return;
  fetch("feed.json", {cache:"no-store"}).then(function (response) {
    if (!response.ok) throw new Error("feed unavailable");
    return response.json();
  }).then(function (data) {
    const score = Number(data.rank_one_public_dti);
    if (!Number.isFinite(score) || score < 0 || score > 1) throw new Error("invalid score");
    const observed = new Date(data.observed_utc);
    const ageHours = (Date.now() - observed.getTime()) / 3600000;
    const freshness = !Number.isFinite(ageHours) || ageHours > 48 || data.status !== "refreshed"
      ? "Dated snapshot — check the official board." : "Recently refreshed snapshot.";
    target.textContent = "Rank 1 public DTI " + score.toFixed(4) + " · observed " + data.observed_utc + ". " + freshness + " Not a receipt for any repository raster.";
  }).catch(function () {
    target.textContent = "Feed unavailable. Open the official leaderboard for current values.";
  });
}());
