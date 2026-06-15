# DataWatch / Hardware-list name cleanup checklist

Generated 2026-06-15 from a live Azure AD ↔ SharePoint Hardware Asset Library
reconciliation (522 AD users × 77 DataWatch cards) plus the names Amit flagged.

**Why this matters:** the report and the mid-week audit auto-map most of these to the
right person, but the *source* stays wrong until corrected here. DataWatch stamps the
name onto each swipe at swipe time, so a correction only cleans swipes made **after**
it — fix early in the week for the cleanest report.

> The Thursday name-audit (`name-audit.yml`) emails joe.ghaleb the **live** typo/split
> list each week from the actual badge log. This file is the standing backlog +
> the SharePoint-side housekeeping (card numbers), which the badge-log audit can't see.

---

## A. D3000 cardholder renames (fix First/Last on the cardholder record)
- [ ] **Arhun Kesiraju → Arjun Kesiraju**
- [ ] **Honey Warma → Honey Varma** (renamed 2026-06-08 — confirm no 2nd credential still "Warma")
- [ ] **Jim Rader → James Rader** (see dup-card consolidation in B)
- [ ] **Ray Dong → Ray Duong**

## B. Duplicate cards — same person, consolidate (D3000)
- [ ] **James Rader** has two cards: **36977** (created by A.Admin5, 06/08/2026) and
      **34160** (created by TSWilliams, 04/01/2026). Keep one active, recall/disable the
      other, and make sure both records spell **"James Rader"** (not "Jim").

## C. Spare / temporary fobs — recall or rename (D3000)
- [ ] **Spare Mitchel Office** — temp fob issued to Mitchell after he lost his.
      Recall it once he finds the original, or rename it to **Mitchell Crespo** if it's
      now his primary. (The report now drops spare/junk fobs automatically, but the
      audit will keep flagging it until the source is cleared.)

## D. Offboarded still showing
- [ ] **Omi Davis** — offboarded ~last week, was still active that week → "Unknown / Not
      Mapped". Confirm the card is deactivated; he drops off the next report.

## E. SharePoint Hardware Asset Library housekeeping (exact cards)
- [ ] **Blank assignee** — card **264-58234** (DataWatch Card, TechSur Owned): assign a
      holder name or mark it explicitly as a spare.
- [ ] **Aaniya Yadav** — card **274-36979**: real person but **not in Azure AD**. Either
      add her to AD (so she maps + gets a manager) or add her to the tracker exclude list.
- [ ] **Delete the 15 "will be deleted after audit" placeholder cards:**
      274-30791, 274-30793, 274-36090, 274-36091, 274-36094, 274-36973, 274-36976,
      274-36978, 274-47182, 274-47183, 274-47184, 274-51412, 274-51426, 274-51431,
      278-20389.
- [ ] (FYI — already excluded from the tracker, listed for completeness) junk/guest/
      removed holders: Rupinder Yadav (264-58235), Louie Chen (274-51414),
      Guest Fob 1 (274-47188), Guest Fob 2 (274-30794), Guest 3 (278-20391),
      Bravo Handy Man (264-58160), Inventory (274-36975 / 278-20387 / 278-20390).

---

### Prevention (process)
- When you email the DataWatch team to provision Bluetooth/badge access, **paste the
  exact Azure AD display name** (copy from AD, don't retype) so they can't fat-finger it.
- After they reply "created", **spot-check the cardholder name** against AD before the
  next swipe.
- The Thursday audit is the safety net: it tells you what slipped through, each week,
  before Monday's report ships.
