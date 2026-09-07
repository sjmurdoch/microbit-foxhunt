# Cognitive walkthroughs

A record of structured usability walkthroughs of the Radio Treasure Hunt setup tool, the issues each one found, and what changed as a result. Kept so that a later change can see which behaviours are deliberate.

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

---

## 2. Busy Cub Scout leader preparing and running an evening activity

**Date** 2026-09-06 · **Persona** Volunteer Cub leader. 24 Cubs aged 8–10, Wednesday 18:30–20:00 in a scout hut with a field behind it. Has a borrowed box of micro:bits and about twenty minutes before the pack arrives. Not a teacher, has no lesson to deliver and no curriculum to satisfy: wants a game that works, outdoors, in the half-light. Likely to split the pack into sixes and run more than one hunt at once.

**Task sequence walked** decide whether this is an activity or a school exercise → work out where to play → set up boards for *two* simultaneous hunts → print something for the Cubs → run it in a hut with no wi-fi → keep track of which boards belong to which hunt.

The teacher walkthrough (1) already fixed the repetitive set-up loop, and those fixes serve this persona unchanged. What follows is what remained.

### Issues found

**2.1 — The running total lied as soon as a second hunt began (Q4)** — *a genuine bug, and it hit exactly the person the feature exists for*
The tally read "Set up so far: 1 Fox, 9 Hounds — on radio group 16", where the group was taken from *whatever was currently selected*. Running two hunts means changing the group part-way through, which is the whole purpose of that control — and doing so silently relabelled every board set up before the change. The one failure this project documents most insistently is a group mismatch, whose only symptom is silence, so a confidently wrong tally is worse than no tally.
*Fixed:* the tally is computed per radio group — "Group 16: 1 Fox, 5 Hounds · Group 23: 1 Fox, 4 Hounds". The grouping is done in the pure `tallyBoards`, so it is tested rather than eyeballed.

**2.2 — Hounds with no Fox on their group were invisible (Q4)**
A hunt with no Fox cannot work, and once the boards are in a bag there is nothing to see. The app had the information and never used it.
*Fixed:* a group with Hounds and no Fox is flagged in the tally as "no Fox yet".

**2.3 — Nothing explained how to run two hunts (Q1, Q3)**
The radio group control existed and its consequences were described, but the *procedure* was not: pick a group, set up that hunt completely, change the number, do the next. A leader could reasonably conclude they needed two computers, or give up and run one big hunt.
*Fixed:* a short note in step 1 giving the order of operations, and pointing at the tally as the thing that keeps them apart.

**2.4 — The sheets were behind a door marked "Teaching with it" (Q2, Q3)**
The section opened with a paragraph about science lessons and closed with Key Stage 2 curriculum mapping. The 20-minute hunt card — by far the best fit for a pack night — was the third of three buttons under a school-shaped heading. A volunteer with no lesson to plan would skim the whole section.
*Fixed:* retitled "Sheets to print", opening with "whether this is a science lesson or a Wednesday evening activity". The hunt card is listed first and described as the one for a club, a party or a first go; the lesson plan is renamed "Plan for the leader" and its 20-minute running order, safety and kit notes are called out as useful to a pack or troop. The curriculum mapping is kept, because walkthrough 1's teacher needs it — it is now the last sentence rather than the framing.

**2.5 — Indoor expectations were too kind (Q1)**
"Indoors works but is much less predictable" undersells it. This project measured about 1 dB between two metres and five metres indoors — no usable gradient at all. A leader whose first attempt is in the hut on a wet evening will conclude the equipment is broken.
*Fixed:* says plainly that indoors the readings jump about and there is barely any difference between two metres and five, that a hall is fine for a quick game, and that outdoors is where it really works.

**2.6 — No advice for a venue with no wi-fi (Q1)**
A scout hut with no connection is the normal case, and the page is the only way to set boards up.
*Fixed:* added to the pre-hunt checklist: set the boards up before you leave, because once a board has the game it needs nothing but its battery. Deliberately phrased as that, rather than as a claim that this page works offline — a service worker exists and caches the site, but offline operation has never actually been tested, and it remains on the open list in `AGENTS.md`. Telling a volunteer something unverified about the one thing standing between them and a working evening would be the wrong trade.

### Deliberately not changed

* **The curriculum mapping and the lesson plan's structure.** Reframed around, not removed — walkthrough 1's teacher needs both.
* **"Most people should leave this alone" on the radio group.** Added for the teacher, and it might have read as discouraging to the one persona who *should* change it. It survives because the very next sentence names their case, and 2.3 now gives them the procedure.
* **The three-step flow, and every element of the flashing mechanism.** Again no new capability: this round is grouping an existing count correctly, and wording.
* **The order of the flashing buttons.** Fox first, Hound second, even though a leader flashes many more Hounds — Fox first matches the order the tally warns about a missing Fox, and the repeat loop is served by the "set up another board" button rather than by button order.

### Verification

Six tests added, including the per-group tally exercised under node with two hunts running at once, and one asserting the wi-fi advice does not overclaim.

---

## 3. Keen Year 5 pupil with a Hound and the full worksheet

**Date** 2026-09-06 · **Persona** Ten years old, enjoys science, wants to do this properly and get it right. Has been handed a working Hound and the printed investigation worksheet. Has never met a micro:bit, a median, or the idea that an instrument can run out of range.

This persona never opens the setup tool. Their interface is **the printed worksheet and the device itself**, so that is what was walked. No device code was changed: every fix is to the paper.

**Task sequence walked** read the mission → predict → measure at seven distances and plot a line graph → test blocking → test bouncing → discover saturation and use button A → write conclusions → attempt the challenge data.

### Issues found

**3.1 — The graph could not be plotted accurately (Q4)** — *a defect in the sheet itself*
The first graph's vertical gridlines were spaced 40px apart while its axis labels were spaced 38px, so the two drifted apart across the page — by the right-hand edge a gridline sat almost a metre from its label — and there was no gridline at 20 m at all, which is the last reading the table asks for. Worse, pupils record 1, 3 and 5 m, and the grid only had lines at even metres, so three of seven readings had nothing to plot against.
*Fixed:* both graphs regenerated with a line at every metre, aligned to the labels, odd metres drawn fainter so the labelled ones still read clearly. Two tests now assert that every axis label has a gridline at the same coordinate and that the spacing is uniform — the sort of error that is invisible in source and obvious on paper.

**3.2 — "How many bars are lit" invites the wrong count (Q3)**
The display is a 5×5 grid of LEDs that fills row by row. A careful child, asked for "bars", may well count the individual red dots and write 15 where the answer is 3. Every subsequent reading, the graph and the conclusions would follow from that.
*Fixed:* the sheet asks for the number of **lit rows**, "a number from 0 to 5, not the number of little red dots", and the table columns are headed "rows".

**3.3 — "Use the middle one" is ambiguous exactly where precision matters (Q3)**
Meant as the median. To a ten-year-old, "the middle one" of three readings most naturally means the second one taken. The distinction matters here because the whole point of repeating is to survive a wobbling signal, and taking the second reading achieves nothing.
*Fixed:* "put your three numbers in order from smallest to biggest and use the one in the middle — so 3, 5, 4 becomes 3, 4, 5, and the middle is 4."

**3.4 — The attenuator was never reset before measuring (Q1)** — *the one that would have quietly ruined the data*
Part 3 teaches pressing button A, and a keen child will have pressed it while exploring long before then. An attenuated Hound reads several rows low and **nothing on the device says so**. Every reading in Part 1 would have been wrong, consistently, with no way for pupil or teacher to notice — and Part 3 itself opens by asserting that all five rows will be lit at 2 m, which would simply not happen.
*Fixed:* both measuring parts now open by pressing button B, with the reason given. The lesson plan tells the teacher to have every group do it before starting.

**3.5 — No way to record hearing nothing (Q2)**
The beep column offered slow, medium or fast. At the far end of the range there may be no beeps at all, and a child who has been told to fill in every box has nowhere to put that.
*Fixed:* the column reads "slow / medium / fast / none".

**3.6 — The investigation never lets them hunt (Q1)**
The persona's actual goal is to *find the Fox*. The 90-minute worksheet measures from a Fox whose position everyone already knows, and the lesson plan's activities do the same. A pupil who came for a fox hunt does a physics practical and never hunts anything. The keen ones will notice, and they would be right.
*Fixed:* the worksheet closes with "Now play it for real", pointing out that the real game is finding a hidden one and that they now know why each of the three tricks works. The lesson plan gains a five-minute slot to hide it once and let them find it, with the hunt card as the fallback if time has gone.

### Deliberately not changed

* **The device code.** Every fault above was in the paper. Adding, say, an on-screen indication that attenuation is active would be a change to `hound.py` with no way to test it here, and it would alter the device-code version on every board. 3.4 is solved by telling pupils to press B.
* **The order and structure of the investigation.** It builds correctly: measure, then interpret, then discover the limitation. Only the instructions inside it changed.
* **The reading level of the challenge section.** It is meant to stretch, and the 15 m anomaly is meant to be hard.
* **The hunt card**, which was already written for this persona's goal and needed nothing.

### Verification

Six tests added, two of which check the graph geometry directly — every axis label has a gridline at its own coordinate, and gridlines are evenly spaced one metre apart. Those catch a class of error that cannot be seen by reading the file.

---

## 4. Twelve-year-old Scout hunting against the clock

**Date** 2026-09-06 · **Persona** Twelve, competitive, outdoors on a spring evening with a Hound in one hand and the hunt card in the other. Another team has already had a go and there is a time to beat. The prize for finding it is getting to hide it for the next team. Will glance at the card once before setting off and then not again unless something goes wrong — and if it does, will read it *while moving*.

The interface is the hunt card and the device. This persona differs from the pupil in walkthrough 3 in one decisive way: **understanding is not the goal, speed is**, and anything that is not immediately useful gets skipped.

**Task sequence walked** grab card and Hound → start hunting with no information → close in → deal with a full screen → find it → get through the questions → hide it for the next team.

### Issues found

**4.1 — The card said what the tricks were but not when to use them (Q3)** — *the central issue for a user in motion*
The three tricks were presented as a numbered set to be read in order. Someone standing in a field with a beeping box does not have a numbered problem; they have a symptom. Nothing mapped "the screen is full" or "I have no idea which way" onto a trick, so the card had to be re-read and reasoned about at exactly the moment there was no time.
*Fixed:* a one-line lookup at the top, from what is happening to what to do — no beeps → walk somewhere else; beeping but lost → trick 2; screen full → trick 3; fast alarm → look around you, not at the screen. The tricks below are unchanged and still carry the "why".

**4.2 — Silence looked identical to a broken Hound (Q4)**
Out of range the Hound is quiet and its display blank, which is precisely what a flat battery or a mis-flashed board looks like. A team that starts outside the Fox's range has no feedback at all, and the first conclusion is that the kit has failed — the exact reasoning this project's own notes warn against.
*Fixed:* trick 1 now says "Nothing at all? Not broken — just too far. Cross to another part of the area until it starts", and the lookup strip carries the same branch.

**4.3 — The card pointed at the screen right up to the point the screen stops helping (Q3)**
Every instruction was about beeps and bars, including the last one. But a Fox two paces away is found by looking, not by measuring, and the card never said to stop. The attenuator gets you close and then the endgame is different in kind.
*Fixed:* trick 3 ends with "Still full after two presses? It is within a couple of paces. Put the screen down and search with your eyes."

**4.4 — "Turn slowly" is not an instruction to someone racing (Q1)**
Trick 2 depends on turning slowly enough to see the reading dip. To a Scout trying to win, "slowly" is whatever they are already doing.
*Fixed:* "turn all the way round while you count to ten" — a number they can actually follow at speed.

**4.5 — The reflection stood between them and their prize (Q1)**
"Quick think — two minutes at the end" is, to this persona, the boring bit after the interesting bit, and it competes with re-hiding the Fox. It would be skipped, which loses the only part of the card that turns a game into a lesson.
*Fixed:* retitled "answer these three, then you can hide it". The questions are unchanged; they are now the gate to the thing this user already wants.

**4.6 — Hiding it was one line of tactics with the important part missing (Q1, Q4)**
The card treated re-hiding as an afterthought for teams who finished early, though it is this persona's actual goal, and it never mentioned the failure that ends a session for everyone: a Fox nobody can find again.
*Fixed:* a short list — inside the boundary, not inside metal, near a wall is harder because radio bounces, and remember where you put it.

### Space, and what it cost

The card must stay one side of paper, and it had about 8mm of slack. The additions above cost roughly 10mm, so they were paid for rather than simply added: the mission paragraph was cut to one sentence, trick wording tightened, the re-hiding list shortened, and the footer folded onto one line. The "why" sentences in each trick — the implicit science the card exists to carry — were deliberately not touched.

The one-page test caught the overflow immediately, on Letter but not A4, which is exactly the asymmetry it was written for. It failed twice during this round before the trimming was enough.

### Deliberately not changed

* **The three tricks and their explanations.** They are the learning, and shortening them to make room would have traded away the reason the card exists.
* **The hunt log.** A competitive team will fill it in *because* it is a record of their time.
* **The device.** Nothing here needed new behaviour: silence, saturation and the omnidirectional aerial are all real properties, and the fix each time was to say so on the card.
* **The reading level.** Written for a Cub of eight as much as a Scout of twelve; nothing was made terser at the cost of being followable.

### Verification

Six tests added, plus the existing one-page print test at both paper sizes, which did the real work of policing the additions.
