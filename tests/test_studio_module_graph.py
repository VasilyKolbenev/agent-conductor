"""The layering of the Studio's and the desk's modules: what each may import, and no cycle.

This circuit lived in `test_studio_source.py` until that module crossed the line cap. The
permission table and the walk over it are one thing -- nothing else reads the table -- so they
moved together, comments and rows unchanged, and the same modules are judged against the same
permissions as before. What stayed behind is what the other Studio guards import from there:
the list of modules, the panel directory, the boot module's name and the import pattern.

Like that module this is the change-detection half: it reads SOURCE TEXT and says nothing about
what a browser renders.
"""
from __future__ import annotations

import re

from tests.test_studio_source import BOOT, IMPORTS, MODULES, PANEL

#: What each module MAY import -- a permission table, not an obligation. The
#: frontend contract's own column is spelled "May import", and a module that
#: has not yet needed one of its permitted neighbours is not a fault; a module
#: reaching for one it was never granted is.
PERMITTED_IMPORTS = {
    "studio-runstep-copy.js": frozenset(),
    "studio-participant-copy.js": frozenset(),
    "studio-run-docs-copy.js": frozenset(),
    "studio-runs-copy.js": frozenset(),
    "studio-runform-copy.js": frozenset(),
    "studio-view-copy.js": frozenset(),
    "studio-workflow-detail-copy.js": frozenset(),
    "studio-workflow-copy.js": frozenset(),
    "studio-feedback.js": frozenset({"./command-view.js", "./studio-i18n.js"}),
    "studio-feedback-model.js": frozenset({"./studio-model.js", "./command-projection.js"}),
    "studio-feedback-copy.js": frozenset(),
    "studio-notice-copy.js": frozenset(),
    "studio-agents-copy.js": frozenset(),
    'studio-automation-model.js': frozenset({'./studio-taskruns.js', './command-projection.js', './studio-model.js', './studio-automation-providers.js'}),
    'studio-automation-providers.js': frozenset({'./studio-model.js'}),
    'studio-automation-flow.js': frozenset({'./studio-automation-model.js'}),
    'studio-automation-copy.js': frozenset(set()),
    'studio-automation.js': frozenset({'./studio-i18n.js', './studio-automation-model.js', './command-view.js'}),
    'studio-workflowwrite.js': frozenset({'./studio-model.js', './studio-store.js', './command-projection.js'}),
    'studio-draft.js': frozenset({'./studio-model.js'}),

    "studio-scene-model.js": frozenset({"./studio-runread.js"}),
    "studio-taskruns.js": frozenset({"./studio-model.js"}),
    "studio-trace.js": frozenset({"./command-view.js", "./studio-scene-model.js", "./studio-i18n.js"}),
    "studio-bridge.js": frozenset({"./command-view.js", "./studio-i18n.js", "./studio-taskruns.js"}),
    "studio-mounts.js": frozenset(),
    "studio-i18n.js": frozenset({"./studio-runstep-copy.js", "./studio-participant-copy.js", "./studio-run-docs-copy.js", "./studio-runs-copy.js", "./studio-runform-copy.js", "./studio-view-copy.js", "./studio-workflow-detail-copy.js", "./studio-workflow-copy.js", "./studio-automation-copy.js", "./studio-agents-copy.js", "./studio-feedback-copy.js", "./studio-notice-copy.js", "./desk-wizard-copy.js", "./desk-copy.js", "./desk-status-copy.js", "./desk-flow-copy.js", "./desk-feed-copy.js", "./desk-summary-copy.js", "./desk-pult-copy.js"}),
    "studio-preferences.js": frozenset({"./command-view.js", "./studio-i18n.js",
                                        "./desk-hash.js"}),
    "studio-shell.js": frozenset({"./command-view.js", "./studio-i18n.js", "./studio-runhead.js"}),
    #: The Runs header of one read run: its situation line and main action. It asks the step control
    #: which form a row draws (`offeredControl`) instead of keeping a second copy of that rule.
    "studio-runhead.js": frozenset({"./command-view.js", "./studio-i18n.js", "./studio-runstep.js"}),
    "studio-quotas-model.js": frozenset({"./studio-model.js"}),
    "studio-quotas.js": frozenset({"./command-view.js", "./studio-i18n.js"}),
    "studio-quotaflow.js": frozenset(),
    "studio-tasks-model.js": frozenset({"./studio-model.js"}),
    "studio-tasks.js": frozenset({"./command-view.js", "./studio-tasks-model.js", "./studio-i18n.js", "./studio-taskruns.js",
                                  "./studio-runhead.js"}),
    "studio-taskflow.js": frozenset({"./studio-tasks-model.js", "./studio-taskruns.js"}),
    "studio-model.js": frozenset(),
    #: The wire doors import the one thing they translate a refusal with, and no
    #: screen, store or copy module: a door that could reach a screen would be a
    #: second boot module.
    "desk-transport.js": frozenset({"./command-projection.js"}),
    "desk-stream.js": frozenset(),
    #: The desk's boot module: the doors, the catalogue that says a word in the reader's
    #: language, the desk's hash module (the reader and writer of the address), the
    #: boundaries that judge what a read brought (the task list, the run list, the
    #: newest-run rule, and the frozen copy a landed read is kept in), the focus net a
    #: redraw carries a keypress across, and the regions it mounts. It reaches no Studio
    #: screen and no store, and the wire only through the transport -- it holds no door of
    #: its own.
    "desk.js": frozenset({"./desk-transport.js", "./studio-i18n.js",
                          "./desk-hash.js", "./desk-embed.js", "./studio-tasks-model.js",
                          "./studio-model.js", "./studio-taskruns.js", "./studio-draft.js",
                          "./studio-situation.js", "./studio-controls.js",
                          "./studio-focus.js", "./desk-rail.js", "./desk-scene.js",
                          "./desk-feed.js", "./desk-summary.js", "./desk-closing.js",
                          "./desk-pult.js",
                          "./desk-flag-model.js", "./desk-flag.js", "./desk-queue.js",
                          "./desk-pult-flow.js", "./desk-wizard-host.js",
                          "./desk-stream.js", "./desk-flow-host.js", "./desk-people-host.js"}),
    "desk-people-host.js": frozenset({"./command-view.js", "./studio-i18n.js",
      "./desk-time.js", "./studio-model.js", "./studio-runread.js",
      "./studio-quotas-model.js", "./studio-quotaflow.js", "./studio-quotas.js",
      "./studio-people.js", "./desk-transport.js"}),
    "desk-wizard-host.js": frozenset({"./desk-transport.js", "./desk-wizard-model.js",
                                         "./desk-wizard-run.js", "./desk-wizard.js"}),
    #: What a press on the console's queue block means: a pure flow over the door it is handed and
    #: the queue's model. It names no route and no wire word, and imports no door itself.
    "desk-pult-flow.js": frozenset({"./desk-queue-model.js"}),
    #: The words of the console's queue controls: a frozen catalogue that imports nothing.
    "desk-pult-copy.js": frozenset(),
    #: The door of the continue-after flag: the one read and the one write of it, through the
    #: transport's own doors, judged by the flag's model. It names one target and opens no door.
    "desk-flag.js": frozenset({"./desk-transport.js", "./desk-flag-model.js"}),
    #: The door of the project's task queue: its reads and writes, through the transport's own
    #: doors, judged by the queue's model. It opens no door of its own.
    "desk-queue.js": frozenset({"./desk-transport.js", "./desk-queue-model.js"}),
    #: The scene, drawn: `mountScene` only. It hands one frozen run read to the Studio's own
    #: participant deck (the Trace and the Orbit), which is the one module of the Studio's
    #: it reaches, and says its own sentences through the catalogue. It may import no store,
    #: no transport and no other screen.
    "desk-scene.js": frozenset({"./command-view.js", "./studio-i18n.js",
                                "./studio-participants.js"}),
    #: The rail, drawn: `mountRail` only. It reads the word of each row from the status
    #: rules and the newest-run rule, builds elements through the view's helper and says
    #: the words through the catalogue, and may import no store, no transport and no other
    #: screen -- a press is a call to its host.
    "desk-rail.js": frozenset({"./command-view.js", "./studio-i18n.js", "./desk-status.js",
                               "./studio-taskruns.js"}),
    #: The console, drawn: `mountPult` only. It builds elements through the view's helper,
    #: says the words through the catalogue and the times through the time module, and
    #: may import no store, no transport and no other screen -- a press is a call to its
    #: host, and the queue it draws is a read the boot module already judged.
    "desk-pult.js": frozenset({"./command-view.js", "./studio-i18n.js", "./desk-time.js",
                              "./desk-queue-model.js"}),
    #: The desk's own words: a frozen catalogue that imports nothing, spread into the one
    #: table by `studio-i18n.js`.
    "desk-copy.js": frozenset(),
    #: The word of a task's row and its strings: pure, and importing nothing, because the
    #: hub's page takes them whole and may only find the shared modules importing each other.
    "desk-status.js": frozenset(),
    "desk-status-copy.js": frozenset(),
    #: The grammar of the desk's hash, shared with the hub's page for the same reason: it
    #: imports nothing, and `studio-preferences.js` re-exports its two preference functions.
    "desk-hash.js": frozenset(),
    #: Embed mode: whether a hub frames the desk, and the one message it says. Values in and
    #: one call out, so it imports nothing -- the boot module hands it the claim it read.
    "desk-embed.js": frozenset(),
    #: The time of an instant, short and exact, shared with the hub's page: it imports
    #: nothing and reads no clock -- the caller hands it the string the server wrote.
    "desk-time.js": frozenset(),
    #: The task-queue read judged against its shape: values in, a frozen cut or null out. The
    #: boot module reads the queue and hands the answer here, so it imports nothing.
    "desk-queue-model.js": frozenset(),
    #: The continue-after flag judged against its shape, the runs a person may mark and the
    #: body of a save: values in, values out. The boot module hands it what it read, so it
    #: imports nothing.
    "desk-flag-model.js": frozenset(),
    #: The journal of a run read as the rows of the feed: values in, frozen rows out. It takes
    #: the Studio's closed vocabularies (record instants, outcomes, verification states, the
    #: store's document limit) and nothing else; the boot module hands it the run it read.
    "desk-feed-model.js": frozenset({"./studio-runwords.js"}),
    #: The summary's counters, tasks and people: values in, frozen values out. It asks the rail's
    #: own rule for a task's word, the newest-run rule, the scene's reading of a run and the
    #: decision rows of a run read, and shares the feed's reading of the loop pass.
    "desk-summary-model.js": frozenset({"./desk-status.js", "./studio-taskruns.js",
                                        "./studio-scene-model.js", "./studio-runread.js",
                                        "./desk-feed-model.js"}),
    #: The words of the summary: a frozen catalogue that imports nothing, spread into the one
    #: table by `studio-i18n.js`.
    "desk-summary-copy.js": frozenset(),
    #: The summary, drawn: `mountSummary` only. It draws the counters, the strip and the panel of
    #: the model's answers in the catalogue's words and the desk's own time text, through the
    #: shared DOM builder; it reads nothing, names no door and keeps its open/closed memory in its
    #: own DOM.
    "desk-summary.js": frozenset({"./command-view.js", "./studio-i18n.js", "./desk-time.js",
                                  "./desk-summary-model.js"}),
    #: The reads that say whether a task was closed. They go through the door the boot module
    #: hands in, so this module opens none: it judges a run read as the scene does, asks the
    #: summary's model which runs could have been accepted and what a run read says.
    "desk-closing.js": frozenset({"./desk-summary-model.js", "./studio-taskruns.js",
                                  "./studio-situation.js"}),
    #: The words of the feed: a frozen catalogue that imports nothing, spread into the one table
    #: by `studio-i18n.js`.
    "desk-feed-copy.js": frozenset(),
    #: The feed, drawn: `mountFeed` only. It draws the rows of the run read the boot module
    #: hands it, in the catalogue's words and the desk's own time text, through the shared DOM
    #: builder; it reads nothing, names no door and holds no state of its own.
    "desk-feed.js": frozenset({"./command-view.js", "./studio-i18n.js", "./desk-time.js",
                               "./desk-feed-model.js"}),
    #: The wizard's whole state and every way it changes, as pure functions. It
    #: reaches the task model for the one rule that judges a task title, and the
    #: step modules that answer its questions, and nothing else: no DOM builder,
    #: no copy, no transport -- an ask it wants performed is a value it returns.
    "desk-wizard-model.js": frozenset({"./studio-tasks-model.js",
                                       "./desk-wizard-materials.js",
                                       "./desk-wizard-cycle.js",
                                       "./desk-wizard-roles.js",
                                       "./desk-wizard-base.js",
                                       "./desk-wizard-team.js",
                                       "./desk-wizard-input.js",
                                       "./desk-wizard-prep.js",
                                       "./desk-wizard-launch.js",
                                       "./desk-wizard-run.js",
                                       "./desk-wizard-skip.js"}),
    #: What the model and the step adapters share (the order of the steps, the limits, a frozen
    #: change, the words of the documents), so neither imports the other. It reaches the task
    #: model for the title limit and the three step modules for theirs, and nothing above it.
    "desk-wizard-base.js": frozenset({"./studio-tasks-model.js", "./desk-wizard-materials.js",
                                      "./desk-wizard-roles.js"}),
    #: The wizard, drawn: `mountWizard` only. It reads the model's slice and the words, builds
    #: elements through the view's helper, and may import no store, no transport and no other
    #: screen -- an edit is an event it hands to its host.
    "desk-wizard.js": frozenset({"./desk-wizard-model.js", "./desk-wizard-copy.js",
                                 "./command-view.js", "./studio-i18n.js",
                                 "./desk-wizard-draw.js", "./desk-wizard-prepare-view.js",
                                 "./desk-wizard-card.js"}),
    #: The controls every step of the wizard is drawn from (a keyed button, a choice, a control
    #: whose door is not open, a text field, the format of an instant and of a duration). They
    #: build elements through the view's helper and reach nothing else.
    "desk-wizard-draw.js": frozenset({"./command-view.js"}),
    #: Step 5 drawn: the links of the chain, what may be pressed, and what a reloaded page found.
    #: It draws what the model says, through the shared controls, and never a store or a wire.
    "desk-wizard-prepare-view.js": frozenset({"./command-view.js", "./desk-wizard-draw.js",
                                              "./desk-wizard-model.js"}),
    #: Step 6 drawn: the terms card, the countdown, the owner's name and the buttons the slot
    #: allows. It draws what the model says through the shared controls, and never a store or a
    #: wire.
    "desk-wizard-card.js": frozenset({"./command-view.js", "./desk-wizard-draw.js",
                                      "./desk-wizard-model.js"}),
    #: The wizard's RU/EN strings, one frozen catalogue in the shape of the other copy
    #: modules. It imports nothing: text is data, and `studio-i18n.js` spreads it in.
    "desk-wizard-copy.js": frozenset(),
    #: Step 4 as the model sees it: the pure step functions applied to the wizard's state. It
    #: imports the base and the step modules, never the model that imports it.
    "desk-wizard-team.js": frozenset({"./desk-wizard-base.js", "./desk-wizard-cycle.js",
                                      "./desk-wizard-roles.js"}),
    #: Step 2 as pure functions over values the model hands it: what git said,
    #: what the cards would compose. It imports nothing, so the model above it
    #: can never be reached back.
    "desk-wizard-materials.js": frozenset(),
    #: Step 3 the same way: the cards, the preselection and the flow write's body,
    #: from the reads the model hands over. It imports nothing for the same reason.
    "desk-wizard-cycle.js": frozenset(),
    #: Step 4 the same way: the roles of a flow, who may take each, the suggestion and the
    #: instruction fields. It imports nothing for the same reason.
    "desk-wizard-roles.js": frozenset(),
    #: SHA-256 and the id of a document the chain publishes, as a fixed pure function. It imports
    #: nothing, so nothing above it can be reached back.
    "desk-wizard-digest.js": frozenset(),
    #: The wizard's state read once, as the plain facts the chain of step 5 is built from, and
    #: the flow write. It reaches the base, the cycle, the materials and the roles (through the
    #: team adapter) and the chain's own reader of a reloaded page, never the model.
    "desk-wizard-input.js": frozenset({"./desk-wizard-base.js", "./desk-wizard-cycle.js",
                                       "./desk-wizard-materials.js", "./desk-wizard-team.js",
                                       "./desk-wizard-prep.js"}),
    #: Step 5's chain as pure functions over those facts and its own slice. It reaches only the
    #: digest that names a document by its bytes.
    "desk-wizard-prep.js": frozenset({"./desk-wizard-digest.js"}),
    #: Step 6's terms card and what may be pressed, as pure functions over its own slice: the
    #: preview's reading, the slot, the countdown, the authorization. It reaches only the digest
    #: that gives a key its stable bytes.
    "desk-wizard-launch.js": frozenset({"./desk-wizard-digest.js"}),
    #: «Пропустить вперёд» from the card: four idempotent writes derived from the reads, as pure
    #: functions over the card's slice. It reaches the card's own module and nothing else.
    "desk-wizard-skip.js": frozenset({"./desk-wizard-launch.js"}),
    #: The chain applied to the wizard's state, and the same after a reload: the seam the model
    #: calls. It is handed the model's judgement of the four steps and never imports the model.
    "desk-wizard-run.js": frozenset({"./desk-wizard-base.js", "./desk-wizard-cycle.js",
                                     "./desk-wizard-input.js", "./desk-wizard-launch.js",
                                     "./desk-wizard-prep.js", "./desk-wizard-skip.js",
                                     "./desk-wizard-team.js"}),
    #: The «Схема» edits a flow (spec 7.2). The shape holds the facts of flow v1 and pure questions
    #: over one, and imports nothing; the loop sugar, the branches and the edits stand on it and on
    #: each other in one direction, and none of them reaches the wire, a store or the page.
    "desk-flow-shape.js": frozenset(),
    "desk-flow-loops.js": frozenset({"./desk-flow-shape.js"}),
    "desk-flow-branches.js": frozenset({"./desk-flow-shape.js"}),
    "desk-flow-edits.js": frozenset({"./desk-flow-shape.js", "./desk-flow-loops.js",
                                     "./desk-flow-branches.js"}),
    #: The write chain: reads and writes of a cycle through the flow door, one at a time. It applies
    #: the edits and reaches the shape for an empty flow and the comparison of two; never the wire.
    "desk-flowwrite.js": frozenset({"./desk-flow-edits.js", "./desk-flow-shape.js"}),
    #: The quick straight-line mode: rows of role kinds turned into a flow by the edits and by
    #: nothing else. It declares no vocabulary of its own.
    "desk-quickcycle.js": frozenset({"./desk-flow-edits.js", "./desk-flow-shape.js"}),
    #: The flow as the canvas draws it, and the summary before a revision: the branches and the
    #: shape, nothing that touches the page.
    "desk-flow-graph.js": frozenset({"./desk-flow-branches.js", "./desk-flow-shape.js"}),
    #: The rows of the inspector and the way a typed text becomes one edit: the shape's facts and
    #: the branches' numbering, so the model can flush a typed text without reaching the drawing.
    "desk-flow-fields.js": frozenset({"./desk-flow-branches.js", "./desk-flow-shape.js"}),
    #: The words of the «Схема»: data only, like every copy module.
    "desk-flow-copy.js": frozenset(),
    #: The «Схема» is drawn by four modules. The shared pieces reach the catalogue, the panel's model
    #: (for its facts) and the shape; the counter and the rows, the inspector and the frame stand on
    #: them in one direction, and only the frame reaches the canvas. None reaches the wire.
    "desk-flow-draw.js": frozenset({"./command-view.js", "./studio-i18n.js", "./desk-flow-model.js",
                                    "./desk-flow-shape.js"}),
    "desk-flow-diag.js": frozenset({"./command-view.js", "./desk-wizard-draw.js",
                                    "./desk-flow-draw.js"}),
    "desk-flow-inspector.js": frozenset({"./command-view.js", "./desk-flow-fields.js",
                                         "./desk-flow-model.js", "./desk-flow-shape.js",
                                         "./desk-flow-draw.js"}),
    "desk-flow.js": frozenset({"./command-view.js", "./studio-i18n.js", "./studio-canvas.js",
                               "./desk-flow-graph.js", "./desk-quickcycle.js",
                               "./desk-flow-shape.js", "./desk-flow-draw.js",
                               "./desk-flow-diag.js", "./desk-flow-inspector.js"}),
    "desk-flow-host.js": frozenset({"./desk-transport.js", "./desk-flow-model.js",
                                    "./desk-flow.js", "./studio-focus.js"}),
    #: The panel's state and its one table of events: the write chain, the edits, the quick mode,
    #: the rows of the inspector and what a publication changes. It draws nothing and reaches no wire.
    "desk-flow-model.js": frozenset({"./desk-flow-edits.js", "./desk-flow-fields.js",
                                     "./desk-flow-branches.js", "./desk-flow-graph.js",
                                     "./desk-quickcycle.js", "./desk-flowwrite.js",
                                     "./desk-flow-shape.js"}),
    # Pure S2 decoder; the actual store read door composes it with the base model.
    "studio-situation.js": frozenset({"./studio-model.js", "./studio-feedback-model.js",
                                      "./studio-runwords.js"}),
    #: The two ceilings and the judge of a typed ceiling field, split off the
    #: boundary at its line cap when the task binding arrived. It imports
    #: nothing for the boundary's own reason, and the boundary does NOT
    #: re-export it -- that would be an import, and the boundary has none.
    "studio-ceilings.js": frozenset(),
    #: The controls route's whole answer: declared capabilities and what is
    #: protecting the run. It reads the boundary's helpers and nothing else, and
    #: `studio-model` does NOT re-export it -- that would be a cycle.
    "studio-controls.js": frozenset({"./studio-model.js", "./studio-automation-providers.js"}),
    #: What is protecting the step in front of a person, drawn from the words
    #: the server sent. It builds elements, so it reaches the view's element
    #: helper and nothing else -- no store, no model, no copy of any sentence.
    "studio-isolation.js": frozenset({"./command-view.js", "./studio-i18n.js"}),
    #: The focus net under the boot module's render pass, split off it at the
    #: line cap. It reads the focused control and imports nothing.
    "studio-focus.js": frozenset(),
    "studio-participants.js": frozenset({"./studio-feedback.js", "./command-view.js",
                                         "./studio-runread.js", "./studio-runwords.js",
                                         "./command-projection.js", "./studio-rundocs.js",
                                         "./studio-scene-model.js", "./studio-trace.js", "./studio-i18n.js"}),
    "studio-orbit.js": frozenset({"./command-view.js", "./studio-i18n.js"}),
    "studio-edits.js": frozenset({"./studio-ceilings.js"}),
    #: Projections over one run read, and nothing else. It imports nothing for
    #: the reason `studio-model.js` imports nothing: a pure computation that
    #: reached for a neighbour would be able to answer from something other
    #: than the payload it was given.
    #: Where a step sits and which connection joins which. Pure arithmetic,
    #: importing nothing for the boundary's own reason.
    "studio-layout.js": frozenset(),
    "studio-runread.js": frozenset(),
    #: What a publish would change, over two documents a read already
    #: carries. It imports nothing for the same reason: a comparison that
    #: could reach a neighbour could answer from something other than the
    #: two documents it was handed.
    "studio-review.js": frozenset(),
    "studio-store.js": frozenset({"./studio-draft.js", "./studio-model.js", "./studio-runread.js",
                                  "./studio-situation.js",
                                  "./studio-quotas-model.js",
                                  "./studio-tasks-model.js",
                                  "./studio-controls.js",
                                  "./studio-review.js", "./studio-edits.js",
                                  "./studio-rundraft.js",
                                  "./studio-runwrites.js",
                                  "./studio-toolbardraft.js"}),
    #: The Workflow toolbar's own facts -- the folds a person touched, the
    #: start box and the run form as typed -- split off the reducer along the
    #: same seam as the run drafts. Pure state movement, importing nothing.
    "studio-toolbardraft.js": frozenset(),
    #: The document draft's arms, split off the reducer at the line cap along
    #: the step draft's seam. Pure state movement importing nothing, so the
    #: grant adds a leaf and cannot add a ring.
    "studio-rundraft.js": frozenset(),
    #: The writes in flight -- which, and until when -- split off the reducer
    #: at the same cap along the seam the step draft's own comment drew: a
    #: write in flight is not a fact about the draft. Pure state movement,
    #: importing nothing.
    "studio-runwrites.js": frozenset(),
    "studio-view.js": frozenset({"./command-view.js", "./command-projection.js",
                                 "./studio-model.js", "./studio-runform.js",
                                 "./studio-shell.js", "./studio-i18n.js", "./studio-taskruns.js"}),
    #: The form that opens a run, split off the shell view at the line cap. It
    #: sits BELOW the view rather than beside it: the view imports it, and it
    #: imports nothing of the view's, which is what keeps the two out of a cycle.
    "studio-runform.js": frozenset({"./studio-i18n.js", "./command-view.js", "./studio-model.js"}),
    "studio-canvas.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                   "./command-projection.js",
                                   "./studio-model.js",
                                   "./studio-layout.js", "./studio-orbit.js",
                                   "./studio-canvas-edges.js", "./studio-canvas-flow.js"}),
    #: What only a flow draws on the canvas (a step's branch and mark, the caller's palette, no
    #: banner), split off it so the canvas keeps its headroom. It builds elements through the
    #: view's helper and reaches nothing else; the canvas imports IT.
    "studio-canvas-flow.js": frozenset({"./command-view.js"}),
    #: The canvas's edge layer, split off it at the line cap. It draws from the
    #: layout the canvas hands it and the words the catalogue holds, and reaches
    #: nothing else: the canvas imports IT, so a permission back would close a ring.
    "studio-canvas-edges.js": frozenset({"./studio-i18n.js", "./studio-layout.js"}),
    #: The field primitives every control on the inspector is built from. They
    #: sit BELOW the sections and reach nothing: a toolkit that could import a
    #: section would close the ring the split was drawn to open.
    "studio-fields.js": frozenset({"./studio-i18n.js", "./command-view.js"}),
    "studio-sections.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                     "./command-projection.js",
                                     "./studio-ceilings.js",
                                     "./studio-fields.js"}),
    #: The fourth section, on its own. It sits BESIDE the sections rather than
    #: above or below them: neither may import the other, so the two cannot
    #: close into a ring. It is granted the reviewed argument projection for
    #: the reason its neighbour is -- what a step may require and publish is
    #: declared by the capability's schema, and this window reads that rather
    #: than keeping an idea of its own.
    "studio-artifacts.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                      "./command-projection.js",
                                      "./studio-fields.js"}),
    #: The sixth section, on its own, beside the other two for the same
    #: reason: where a step goes next is about to carry conditions, and a
    #: control that offers one belongs with the roads it draws.
    "studio-transitions.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                        "./studio-fields.js"}),
    "studio-inspector.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                      "./command-projection.js",
                                      "./studio-model.js",
                                      "./studio-artifacts.js",
                                      "./studio-fields.js",
                                      "./studio-sections.js",
                                      "./studio-transitions.js"}),
    #: `studio-runread.js` joined the row when the Runs screen had to decide
    #: "is an attempt still unanswered" from the RECORDS rather than from the
    #: runtime phase. It is a projection over one run read and imports nothing,
    #: so the grant adds a leaf and cannot add a ring.
    "studio-runs.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                 "./studio-participants.js", "./studio-runhead.js",
                                 "./command-projection.js",
                                 "./studio-model.js",
                                 "./studio-runwords.js",
                                 "./studio-runread.js",
                                 "./studio-runstep.js",
                                 "./studio-rundocs.js"}),
    #: The document form, the other write on the Runs screen, in its own file
    #: for the step control's reason. It reads the DOM builder, the reviewed
    #: argument projection (which references a plan consumes), the words two
    #: fragments say, and the projection that answers which document a
    #: proposal bound -- and may not import `studio-runs.js` or the step
    #: control: the screen imports both, and either edge back is a ring.
    "studio-rundocs.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                    "./command-projection.js",
                                    "./studio-runwords.js",
                                    "./studio-runread.js"}),
    #: The two controls that WRITE, on their own beneath the screen that draws
    #: them. It reaches the DOM builder, the canonical-text function it shows a
    #: plan's arguments with, and the module that declares the sentences two
    #: screens say -- and nothing else. It is granted no model and no transport,
    #: and it may not import `studio-runs.js`: the screen imports IT, and a
    #: permission the other way is what would close the pair into a ring.
    #: The step control reads which arguments are INPUTS from the document
    #: form's one rule (`inputRefs`), so the two cannot disagree about what a
    #: step reads. The form imports nothing of the step control's, which is
    #: what keeps the pair out of a ring.
    "studio-runstep.js": frozenset({"./studio-i18n.js", "./command-view.js",
                                    "./command-projection.js",
                                    "./studio-runwords.js",
                                    "./studio-runread.js",
                                    "./studio-isolation.js",
                                    "./studio-rundocs.js"}),
    #: What a press on one of those controls MEANS, split off the boot module
    #: when it reached the line cap. It reaches the two fragments' own
    #: sentences and NOTHING else: no DOM builder, no model, and above all no
    #: transport -- the boot module hands it a `write` and keeps every socket.
    "studio-runwrite.js": frozenset({"./studio-runstep.js",
                                     "./studio-rundocs.js"}),
    #: The Runs screen's closed vocabularies, each a copy of exactly one
    #: Python owner. It imports NOTHING, for `studio-model.js`'s reason: a
    #: list this build must hold equal to a Python module may not be able to
    #: answer from anything but itself.
    "studio-runwords.js": frozenset(),
    #: The Decisions and Agents screens. `studio-runwords.js` joined the row
    #: when the AND-join sentence had to be said on two screens: this one says
    #: it about a gate that cannot be answered yet and the Runs screen says it
    #: about a step that is not offered, and one rule said twice in two files
    #: is one rule that can be said two ways. The grant is to the words module
    #: alone -- never to `studio-runs.js`, which would put two screens in one
    #: ring.
    "studio-people.js": frozenset({"./command-view.js", "./studio-i18n.js",
                                   "./studio-quotas.js",
                                   "./command-projection.js",
                                   "./studio-model.js",
                                   "./studio-runwords.js"}),
    "studio.js": frozenset(
        {f"./{name}" for name in MODULES if name != BOOT}
        | {"./command-view.js", "./command-projection.js"}),
}


def test_the_studio_module_graph_is_acyclic_and_stays_inside_its_permissions():
    """The layering, spelled as import permissions so a cycle cannot hide.

    Acyclicity is COMPUTED from the edges that are really there rather than
    inferred from the table: a permission table alone would allow a cycle the
    moment two modules were both permitted each other.
    """
    edges: dict[str, set[str]] = {}
    for name in MODULES:
        found = set(re.findall(IMPORTS, (PANEL / name).read_text(encoding="utf-8")))
        assert found <= PERMITTED_IMPORTS[name], (
            name, sorted(found - PERMITTED_IMPORTS[name]))
        edges[name] = {target[2:] for target in found if target[2:] in MODULES}
    seen: set[str] = set()
    stack: set[str] = set()

    def walk(node: str) -> None:
        assert node not in stack, f"import cycle through {node}"
        if node in seen:
            return
        stack.add(node)
        for target in sorted(edges[node]):
            walk(target)
        stack.discard(node)
        seen.add(node)

    for name in MODULES:
        walk(name)
