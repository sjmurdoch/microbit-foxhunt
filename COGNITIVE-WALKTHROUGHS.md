# Cognitive walkthroughs

A record of structured usability walkthroughs of the Fox Hunt flasher, the issues each one found, and what changed as a result. Kept so that a later change can see which behaviours are deliberate.

The method is the standard one. For each step a user must take, ask four questions:

1. Will the user try to achieve the right result?
2. Will the user notice that the correct action is available?
3. Will the user associate the correct action with the result they are trying to achieve?
4. If the correct action is performed, will the user see that progress is being made?

A "no" to any of them is a defect, and the interesting ones are usually 3 and 4.

The app has several audiences — the project's own maintainers, scout and club leaders, curious hobbyists, and teachers. A fix for one must not cost another, so each entry below notes what was deliberately left alone.

---

## 1. Busy primary teacher preparing and running a lesson

**Date** 2026-09-06 · **Persona** Year 5 teacher. Has a cupboard box of mixed micro:bits, a free lunchtime to prepare, and a Thursday afternoon to run the session with 30 children in pairs. Has not used a micro:bit before, is not a programmer, and is doing this between two other jobs.

**Task sequence walked** decide whether to use this at all → work out what is needed → sort V2 boards from V1 in the box → set the radio group → set up 16 boards → print the sheets → on the day, check the Fox works → diagnose a hound that "is not working".

### Issues found

**1.1 — "How long is this going to take me?" (Q1)**
Nothing on the page said. A teacher with 25 minutes of lunch left cannot tell whether to start. The project has measured this precisely — 22.7 s for the first flash of a board, 1.4–2.5 s afterwards — and was not telling anyone.
*Fixed:* the introduction now says to allow about half a minute for the first board and a few seconds after, and that a class set takes a few minutes. It also states the quantity needed: one Fox, one Hound per group of children.

**1.2 — Step 1 asks a question the user cannot yet answer (Q1, Q2)**
The first interactive element was a numeric radio-group input, presented as step 1 of 3. For almost every teacher the correct action is *to do nothing*, but the page implied a decision was required, inviting either paralysis or an arbitrary number.
*Fixed:* step 1 now opens with "Most people should leave this alone", and explains the exception — another class or group hunting nearby. The reason it matters is kept, but after the reassurance rather than before it.

**1.3 — The V1 refusal explained itself to a programmer (Q3)**
Connecting an older board produced: *"V1 has no speaker, and on V1 `radio.config(power=)` resets the radio group, which the fox changes three times a second."* Accurate, and useless to someone holding a box of boards. It also never said what a V2 looks like, so the user could not act on it.
*Fixed:* plain language, and it now describes the physical difference — gold logo on the front, notches in the gold strip along the bottom edge. This is the single message most likely to be read by someone who has never seen a micro:bit.

**1.4 — After a successful flash, the next step was somewhere else (Q2, Q3)** — *the most costly issue found*
The success message appeared at the bottom of step 3. The action needed to continue, "Done with this board", was a secondary button at the top of step 2, well away from where the user was looking and worded as an ending rather than a continuation. Setting up sixteen boards meant re-finding that button sixteen times, and nothing suggested what to do physically.
*Fixed:* the success message now carries a primary button, "Done — set up another board". It releases the board, reports how many are done, tells the user to unplug this one and plug in the next, and scrolls the Connect button into view. The old button remains for anyone who wants to stop.

**1.5 — No sense of progress through a repetitive task (Q4)**
The only feedback was a table of truncated USB serial numbers titled "Boards flashed in this session" — an identifier no teacher has any use for, listing every flash rather than every board. Someone halfway through a box had no way to answer "how many have I done, and did I remember the Fox?"
*Fixed:* a running tally — "Set up so far: 1 Fox, 9 Hounds — on radio group 16". Counts are per *board*, not per flash: reflashing a board that was set up wrongly corrects the count instead of inflating it. The table is numbered, headed "N boards set up", and keeps the serial as secondary text for anyone matching against `make devices`.

**1.6 — The Fox check was named after its mechanism (Q3)**
The button read "Radio monitor…". A teacher looking for "is my Fox actually working before I hide it?" would not connect the two, and might reasonably fear it was a developer tool.
*Fixed:* relabelled "Check the Fox is working…", and the panel explains what it is for before warning what it does. The warning that it replaces the game is unchanged — it is a real consequence and must stay prominent.

**1.7 — A wrong radio group was detectable but not reported (Q4)**
Connecting a board already showed its group, but the page never compared it to the group selected above. This is the failure the project documents most insistently: two boards on different groups produce silence and no error. A teacher diagnosing a hound that "does not work" had the answer on screen as a bare number and no reason to notice it.
*Fixed:* a mismatch now produces an explicit warning naming both groups, stating that boards on different groups cannot hear each other and that nothing on the board says so, and what flashing will do about it.

**1.8 — A message written into a section that had just been hidden (Q4)** — *found by walking it, not by reading it*
Implementing 1.4 surfaced a latent bug. Tearing down the board panel hides the whole "Flash it" section, and `#result` — where the app wrote "N boards done, unplug this one and plug in the next" — lives inside it. The most important feedback in the repeat-flashing loop would have rendered into a hidden element and never been seen. The same fault affected the message shown when the device chooser comes up empty.
*Fixed:* a `#next-prompt` element in the always-visible connect section, and both messages now go there. A test asserts it sits outside the section that gets hidden.

### Deliberately not changed

* **The three-step structure.** Renumbering or collapsing steps would help a repeat user and hurt a first-time one. The repetition problem was fixed inside step 3 instead.
* **The warning that the Fox check replaces the game.** It is alarming, and correctly so.
* **The radio group control itself.** Reassurance was added around it; it was not hidden behind an "advanced" toggle, because for a scout leader running two hunts in one park it is the most important control on the page.
* **The USB serial number.** Demoted, not removed — it is how a maintainer matches a board against `make devices` output.
* **Anything about the flashing mechanism.** No new capability was added; every change is to wording, placement or feedback.

### Verification

Seven tests added in `test_site.py`, including one that runs the pure `tallyBoards` under node and asserts that a board flashed as Fox and then corrected to Hound counts once, as a Hound. The others pin the wording and placement outcomes so they are not silently reverted.
