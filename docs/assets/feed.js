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
    if (!Number.isFinite(observed.getTime())) throw new Error("invalid observation date");
    const ageHours = (Date.now() - observed.getTime()) / 3600000;
    let freshness;
    if (data.status === "refresh_result_unverified") {
      freshness = "A scheduled refresh ran, but its deployed result is not verifiable in this repository; check the official board.";
    } else if (data.status === "refreshed" && ageHours >= 0 && ageHours <= 48) {
      freshness = "Recently refreshed snapshot.";
    } else {
      freshness = "Dated snapshot — check the official board for the current value.";
    }
    target.textContent = "Last recorded rank 1 public DTI " + score.toFixed(4) +
      " · observed " + data.observed_utc + ". " + freshness +
      " This public-board value is not a receipt for any repository raster.";
  }).catch(function () {
    target.textContent = "Leaderboard feed unavailable. Open the official leaderboard for the current value.";
  });
}());
