#!/usr/bin/env python3
"""Build the static Pages site from the pinned audit and negative run card.

This builder cannot promote a file. A future selector must be designed and
reviewed separately before any positive download status is supported.
"""
from __future__ import annotations
import html
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
H = html.escape


def link(url: str, text: str, classes: str = "") -> str:
    return f'<a{f" class={chr(34)}{H(classes, quote=True)}{chr(34)}" if classes else ""} href="{H(url, quote=True)}">{H(text)}</a>'


def frame(title: str, content: str, active: str) -> str:
    nav = [
        ("index.html", "Overview"),
        ("executive-summary.html", "Submission guide"),
        ("evidence.html", "Evidence & sources"),
    ]
    navigation = "".join(
        '<a href="{}"{}>{}</a>'.format(H(url), ' aria-current="page"' if url == active else '', H(label))
        for url, label in nav
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><meta name="description" content="Evidence-first research on the DOE GEMS fault-mapping challenge.">
<title>{H(title)} | GEMS Field Notes</title><link rel="stylesheet" href="assets/site.css"><script src="assets/app.js" defer></script></head>
<body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><div class="shell nav"><a class="brand" href="index.html" aria-label="GEMS Field Notes home"><span class="brand-mark" aria-hidden="true">G<span>•</span></span><span>GEMS<span class="brand-sub">FIELD NOTES</span></span></a><nav aria-label="Main navigation">{navigation}</nav><a class="nav-cta" href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">Official leaderboard <span aria-hidden="true">↗</span></a></div></header>
<main id="main">{content}</main>
<footer><div class="shell footer"><div><a class="brand footer-brand" href="index.html"><span class="brand-mark" aria-hidden="true">G<span>•</span></span><span>GEMS<span class="brand-sub">FIELD NOTES</span></span></a><p>Evidence first. Predictions second.</p></div><p>Independent project · Not affiliated with DOE, USGS, or DrivenData.<br>Historical figures are unverified unless specifically identified otherwise.</p><div class="footer-links"><a href="evidence.html">Evidence</a><a href="https://github.com/kanlerxz87-cyber/KANLERGEMSDOE1">Repository ↗</a></div></div></footer>
</body></html>'''


def validate_negative_evidence(manifest: dict, audit: dict, card: dict) -> None:
    """Refuse to publish this fixed negative decision if its inputs change."""
    if (card.get("verdict") != "negative" or card.get("raster_sha256") is not None
            or card.get("weekly_slot_selected") is not False
            or card["holdout"]["value"] is not None or card["holdout"]["ci95"] is not None
            or not card["validator_output"]["status"].startswith("NOT RUN")):
        raise ValueError("This site builder cannot authorize or invent a candidate, score or validation.")
    sites = manifest["sites"]
    if len(sites) != 9 or set(audit["sites"]) != {s["id"] for s in sites}:
        raise ValueError("focus manifest and audit do not agree")
    if any(audit["sites"][s["id"]]["sha256"] != s["sha256"]
           or audit["sites"][s["id"]]["literal_peer_gate_pass"] is not False for s in sites):
        raise ValueError("focus hashes or negative peer verdicts changed; review the site text")
    lattice = audit["lattice"]
    fixed = (audit["footprint_pixels"], lattice["within_3px_pixels"], lattice["outside_3px_pixels"],
             lattice["capacity_at_h33_budget"]["positive_dots"],
             lattice["capacity_at_h33_budget"]["first_impossible_count"],
             audit["h33_lineage"]["h33_xor_d28_beyond_2px"])
    if fixed != (5167373, 5160724, 6649, 37654, 22164, 0):
        raise ValueError("audit numbers changed; review the fixed site narrative")
    current = audit["current_sibling_claim_reviews"]
    if (round(current["GEMSDOE27-H31"]["overlap_with_r13_lattice"] * 100, 2) != 99.61
            or round(current["GEMSDOE31-H31X"]["overlap_with_r13_lattice"] * 100, 2) != 99.34):
        raise ValueError("sibling claim results changed; review the fixed site narrative")


def main() -> None:
    manifest = json.loads((ROOT / "registry/focus_sites.json").read_text())
    audit = json.loads((ROOT / "evidence/focus-site-audit-20261026.json").read_text())
    card = json.loads((ROOT / "evidence/run-card.json").read_text())
    validate_negative_evidence(manifest, audit, card)
    sites = manifest["sites"]
    rows = []
    for s in sites:
        measure = audit["sites"][s["id"]]
        if measure["sha256"] != s["sha256"]:
            raise ValueError("focus hash does not match audit")
        download = f"https://github.com/{s['repo']}/blob/{s['ref']}/{quote(s['path'], safe='/')}?raw=true"
        filename = s["path"].split("/")[-1]
        aliases = measure["exact_support_peers"]
        note = ("Exact mask also on " + ", ".join(aliases)) if aliases else f"Nearest peer: {measure['max_focus_peer']}"
        rows.append(f'''<tr data-repo="{H(s['repo'], quote=True)}" data-ref="{H(s['ref'], quote=True)}">
<td><a class="site-name" href="{H(s['site'], quote=True)}">{H(s['id'])} ↗</a><span class="freshness" aria-live="polite">Checking GitHub head…</span></td>
<td><a class="file-link" href="{H(download, quote=True)}">{H(filename)}</a><span class="subtext">Historical file · research only</span></td>
<td><span class="claim">{H(s['reported_claim'])}</span><span class="subtext">User-reported claim, unverified</span></td>
<td><span class="muted-strong">Not estimable</span><span class="subtext">No calibrated forecast</span></td>
<td><span class="no-tag">NO</span><span class="subtext">{measure['max_focus_peer_overlap']:.1%} near a peer<br>{H(note)}</span></td>
<td><span class="status-no">Do not submit</span></td></tr>''')
    audit_text = json.dumps(audit, indent=2, allow_nan=False) + "\n"
    card_text = json.dumps(card, indent=2, allow_nan=False) + "\n"
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "data/focus-site-audit.json").write_text(audit_text)
    (DOCS / "data/run-card.json").write_text(card_text)
    table = "\n".join(rows)
    overlap = audit["lattice"]["capacity_at_h33_budget"]["min_overlap_fraction"]
    content = f'''<section class="hero"><div class="shell hero-grid"><div class="hero-copy"><div class="eyebrow"><span class="eyebrow-dot"></span> DOE GEMS PRIZE · RESEARCH BRIEF</div><h1>Find the fault.<br><em>Keep the evidence.</em></h1><p class="hero-lede">A clearer way to assess fault-mapping submissions, compare nine research sites, and protect your next leaderboard attempt.</p><div class="hero-actions"><a class="button button-dark" href="executive-summary.html">Read the submission guide <span aria-hidden="true">↗</span></a><a class="text-link" href="#portfolio">Explore the nine-site review <span aria-hidden="true">↓</span></a></div><div class="hero-note"><span class="mini-icon" aria-hidden="true">✓</span> Evidence-backed decisions, not a projected score.</div></div>
<aside class="decision-card" aria-labelledby="decision-title"><div class="decision-top"><span class="card-kicker">SUBMISSION STATUS</span><span class="status-pill"><span></span> BLOCKED</span></div><div class="decision-icon" aria-hidden="true">!</div><h2 id="decision-title">No file approved<br>for submission.</h2><p>No new TIFF was generated in this run. The uniqueness rule and missing shared evidence prevent a safe recommendation.</p><button class="download-disabled" type="button" disabled>↓ &nbsp; Submission download unavailable</button><a class="decision-link" href="executive-summary.html#why-blocked">See the exact blockers <span aria-hidden="true">→</span></a><div class="card-foot">AUTOMATED REVIEW <span>·</span> NO SLOT SELECTED</div></aside></div></section>
<section class="metric-strip"><div class="shell metrics"><div><span class="metric-label">PUBLIC LEADERBOARD SNAPSHOT</span><strong>0.4437 <small>↗</small></strong><span class="metric-caption">Observed 26 Oct, ~21:37 UTC · not a file receipt</span></div><div><span class="metric-label">FOCUS REPOSITORIES</span><strong>09</strong><span class="metric-caption">Pinned historical files audited</span></div><div><span class="metric-label">NEW SUBMISSION SLOTS USED</span><strong>00</strong><span class="metric-caption">No upload or selection made</span></div><div><span class="metric-label">OUR SCORE ESTIMATE</span><strong class="metric-word">Unknown</strong><span class="metric-caption">No defensible calibration available</span></div></div></section>
<section class="section shell" id="decision"><div class="section-head"><div><p class="section-index">01 / THE DECISION</p><h2>The short version.</h2></div><p class="section-intro">A valid file is not automatically a good experiment. We separate format, scientific evidence, novelty, and permission to use a weekly slot.</p></div>
<div class="insight-grid"><article class="insight insight-dark"><span class="insight-number">01</span><h3>The leader is a reference,<br>not a candidate.</h3><p>The reported H33 association is unverified. Its file is an exact catalogue-distance-pruned subset of another historical raster—not a newly independent detector.</p><a href="evidence.html#h33">Understand H33 <span aria-hidden="true">↗</span></a></article><article class="insight"><span class="insight-number">02</span><h3>The novelty gate<br>is binding.</h3><p>A registered calibration lattice covers almost the entire mirrored footprint. At the H33 dot budget, even the theoretical minimum overlap is {overlap:.2%}—above the 70% limit.</p><a href="evidence.html#uniqueness">See the calculation <span aria-hidden="true">↗</span></a></article><article class="insight"><span class="insight-number">03</span><h3>Protect the next<br>weekly slot.</h3><p>Mirrored inputs were restored, but the shared feature stack and authenticated sample remain unverified. Reproduced shared gate and holdout defects block safe evaluation and promotion.</p><a href="executive-summary.html#why-blocked">Review the gates <span aria-hidden="true">↗</span></a></article></div></section>
<section class="section portfolio-section" id="portfolio"><div class="shell"><div class="section-head"><div><p class="section-index">02 / NINE-SITE PORTFOLIO</p><h2>History, without the hype.</h2></div><p class="section-intro">The numbers below are owner/user claims, <strong>not organizer-confirmed scores</strong>. No historical file is recommended as a new submission.</p></div>
<div class="table-card"><div class="table-heading"><div><h3>Historical best listed per site</h3><p>Each file is linked to its pinned historical bytes, for research only.</p></div><a class="outline-button" href="data/focus-site-audit.json">Download audit JSON <span aria-hidden="true">↓</span></a></div><p class="mobile-scroll">Swipe sideways to see the full table →</p><div class="table-scroll" role="region" tabindex="0" aria-label="Scrollable historical site table"><table><thead><tr><th scope="col">Site &amp; freshness</th><th scope="col">Historical file</th><th scope="col">Historical claim</th><th scope="col">Leaderboard estimate</th><th scope="col">Unique vs peers?</th><th scope="col">Action</th></tr></thead><tbody>{table}</tbody></table></div><div class="table-foot"><span>Overlap = fraction of this file's dots within 3 px of its nearest other focus file. Surface uniqueness was not replayed.</span><span class="feed-label" id="feed-state" aria-live="polite">GitHub freshness: checking…</span></div></div>
<div class="disclaimer"><span aria-hidden="true">i</span><p><strong>What this does—and does not—prove.</strong> The table compares nine pinned raster supports, not every concurrent registry file or the original pre-placement surfaces. GitHub head checks show source changes only; they do not refresh scores or certify newly changed files.</p></div></div></section>
<section class="section shell"><div class="section-head compact"><div><p class="section-index">03 / WHAT HAPPENS NEXT</p><h2>From idea to entry.</h2></div><a class="outline-button" href="evidence.html">Open research notes <span aria-hidden="true">↗</span></a></div><div class="process-grid"><div><span class="process-no">01</span><h3>Resolve the shared gates</h3><p>Fix shared preview-gate and holdout defects upstream and agree registry scope centrally.</p></div><div><span class="process-no">02</span><h3>Test the geology</h3><p>Run feature canaries and buffered, visible-only spatial holdout against a matched control.</p></div><div><span class="process-no">03</span><h3>Verify exact bytes</h3><p>Check the authoritative grid, values and saved TIFF before a separate slot selector acts.</p></div></div></section>'''
    (DOCS / "index.html").write_text(frame("Overview", content, "index.html"))
    guide = '''<section class="page-hero"><div class="shell"><p class="section-index">EXECUTIVE SUMMARY / SUBMISSION GUIDE</p><h1>Before you submit,<br><em>know the gates.</em></h1><p>A clear path from a validated research artifact to an eligible competition entry. Right now, that path is blocked.</p></div></section>
<section class="section shell guide-layout"><div><div class="callout-stop" id="why-blocked"><span class="status-pill"><span></span> DO NOT SUBMIT</span><h2>There is no approved file to download.</h2><p>No candidate was built in this run. The shared feature stack is missing, the pre-placement gate and holdout evaluator have reproduced defects, and the literal lattice rule rules out the usual 37,654-dot budget. Historical files are reference material only.</p><a href="data/run-card.json">Open the run card ↗</a></div><h2 class="guide-heading">When a future file is approved</h2><ol class="steps"><li><div><h3>Confirm the decision and quota</h3><p>The candidate must pass both novelty stages, individual feature canaries, a paired spatial holdout, and the saved-byte format checks. A separate selector must approve a slot within the user’s cap. The remaining quota is not available here; <a href="https://community.drivendata.org/t/submission-amount-question/11553/2">staff say the competition website limit prevails</a> over the rules’ three-per-week parenthetical.</p></div></li><li><div><h3>Download the exact approved TIFF</h3><p>Use the link and SHA-256 from that future decision. Do not rename an old TIFF or submit a PDF, audit JSON, or screenshot. If a download is packaged as a ZIP, extract the GeoTIFF; the official format specifies a GeoTIFF, not a ZIP upload.</p></div></li><li><div><h3>Check the official format</h3><p>The written specification calls for one float32 band, EPSG:32611, matching bounds and 100 m grid, values in [0,1], and null/NaN outside the bounds. The exact shape and transform must match an authenticated competition template. Local validation does not prove portal acceptance.</p></div></li><li><div><h3>Use the competition form</h3><p>Enroll and sign in on DrivenData, open the competition’s Submit page, choose the approved GeoTIFF, and enter its short name and note where requested. Check your weekly limit on that page before proceeding.</p></div></li><li><div><h3>Save the receipt</h3><p>Record the file SHA-256, name, note, date and organizer score from the submission page. Only then can a result be attributed to those exact bytes. Choose one final entry for both prize rounds.</p></div></li></ol>
<div class="range-box"><p class="section-index">TROUBLESHOOTING</p><h3>“Predicted values must be in range [0, 1]”</h3><p>Non-finite or out-of-range values <em>inside</em> the footprint, including floating-point nodata sentinels, fail local checks. The specific cause of the reported portal error is unverified. Do not assume zero outside is accepted: the written specification asks for null/NaN outside. Confirm the exact template and organizer guidance before trying again.</p></div></div><aside class="guide-aside"><div class="aside-card"><p class="section-index">REQUIRED CHECKS</p><ul class="gate-list"><li><span>01</span> Assigned method lane</li><li><span>02</span> Every-feature leakage canary</li><li><span>03</span> Paired spatial holdout + CI</li><li><span>04</span> Surface and final-dot novelty</li><li><span>05</span> Exact-file format validation</li><li><span>06</span> Separate quota-aware selector</li></ul><p class="aside-note">No human geological inspection is used as a substitute for these automated checks.</p></div><a class="aside-source" href="https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/">Read the official submission format ↗</a><a class="aside-source" href="https://docs.nlr.gov/docs/fy26osti/96647.pdf">Read the official rules ↗</a></aside></section>'''
    (DOCS / "executive-summary.html").write_text(frame("Submission guide", guide, "executive-summary.html"))
    evidence = '''<section class="page-hero"><div class="shell"><p class="section-index">EVIDENCE / RESEARCH NOTES</p><h1>What we know.<br><em>What we don't.</em></h1><p>Traceable inputs and clear uncertainty, so the next experiment starts from a stronger foundation.</p></div></section>
<section class="section shell evidence-layout"><div><article class="evidence-block" id="h33"><p class="section-index">01 / H33 FORENSICS</p><h2>A useful geometry, not a proven cause.</h2><p>On the pinned owner mirrors, H33's 37,654 dots exactly equal the 44,090-dot D2.8 raster after removing the 6,436 dots within two pixels of mapped faults. No score-to-file receipt was found. A missing receipt does not prove a later score did not occur.</p><p>The official metric gives each true-fault pixel the strongest nearby prediction, while false-positive mass accumulates. Thinning redundant dots or pruning low-yield ones can help—but hidden labels and authenticated receipts are required to establish whether they did. The organizer confirms the known-fault mask is pixel-exact and new faults can lie close to known faults.</p><a class="inline-link" href="https://community.drivendata.org/t/scoring-clarification-are-known-usgs-ingenious-faults-masked-when-scoring-and-are-they-in-the-final-round-label-set/11516/4">Organizer mask clarification ↗</a></article>
<article class="evidence-block" id="uniqueness"><p class="section-index">02 / REGISTRY CONSTRAINT</p><h2>A literal rule with a real consequence.</h2><p>A registered lattice is within three pixels of 5,160,724 of the 5,167,373 cells in the mirrored footprint. Only 6,649 cells are outside its reach. For N distinct candidate dots, at least <code>max(0, N − 6,649)</code> must be near it.</p><div class="formula"><span>AT H33'S DOT BUDGET</span><strong>82.34% minimum</strong><small>Required threshold: ≤ 70% · bound applies before any model is run</small></div><p>Any candidate of at least 22,164 dots must fail that literal lattice comparison. Smaller candidates might pass; no candidate-specific test was performed. A centralized decision on registry scope—not a private exemption—is required.</p><p>Two sibling pages offer H31 / H31-X as eligible under narrower criteria, but the pinned files have 99.61% / 99.34% lattice overlap. Under this prompt's literal rule both remain <strong>do not submit</strong>; GEMSDOE31 also contains conflicting decision banners.</p><a class="inline-link" href="data/focus-site-audit.json">Inspect the reproducible audit ↗</a></article>
<article class="evidence-block"><p class="section-index">03 / RESEARCH LANE</p><h2>Test a different physical mechanism.</h2><p>The proposed HC3 lane tests paired hydrochemical contrasts across coherent magnetic or gravity edges, with sampling-effort controls. It may indicate an under-cover permeable or sealing fault; groundwater mixing at an ordinary lithologic contact is an explicit competing explanation. It is a hypothesis, not a detected fault or projected score.</p><p>Our input is a public-data mirror, not independently authenticated official competition data. The 35-channel shared cache, per-feature canaries and paired holdout are missing. No experiment was run and no TIFF was generated.</p><a class="inline-link" href="https://github.com/kanlerxz87-cyber/KANLERGEMSDOE1/blob/main/research/preregistration.md">Read all four ranked hypotheses ↗</a></article>
<article class="evidence-block"><p class="section-index">04 / DATA &amp; SOFTWARE</p><h2>Do not confuse a hash with provenance.</h2><p>Four owner-mirrored files were restored and hash checked; the shared preparation script was run. The mirrored “sample” contains the known-fault mask, while the problem page describes a total-absence example. Separately, the shared pre-placement gate ignores excessive preview overlap, and the shared holdout can omit false positives in zero-truth cells. The shared writer also binarizes probabilities. These issues are <a href="https://github.com/buffedlizard55-lab/GEMSDOE32/issues/42">reported upstream</a>, not silently patched here.</p><a class="inline-link" href="https://github.com/kanlerxz87-cyber/KANLERGEMSDOE1/blob/main/research/review-and-next-steps.md">Read the full audit and next steps ↗</a></article></div>
<aside class="sources"><div class="aside-card"><p class="section-index">TRUSTED STARTING POINTS</p><h3>Official sources</h3><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/">Problem &amp; metric <span>↗</span></a><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">Live leaderboard <span>↗</span></a><a href="https://docs.nlr.gov/docs/fy26osti/96647.pdf">Official rules PDF <span>↗</span></a><a href="https://github.com/drivendataorg/gems-prize-reference-solution">Reference solution <span>↗</span></a><a href="https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and">USGS GeoDAWN <span>↗</span></a><a href="https://gdr.openei.org/submissions/1391">DOE GDR · INGENIOUS <span>↗</span></a><a href="https://www.usgs.gov/3d-elevation-program">USGS 3DEP <span>↗</span></a></div><p class="sources-note">The leaderboard is linked, not automatically scraped: DrivenData's terms prohibit automated monitoring. GitHub freshness checks are best effort and show repository changes only.</p></aside></section>'''
    (DOCS / "evidence.html").write_text(frame("Evidence and sources", evidence, "evidence.html"))
    print("Built docs/index.html, docs/executive-summary.html and docs/evidence.html (negative decision only).")


if __name__ == "__main__":
    main()
