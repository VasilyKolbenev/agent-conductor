"use strict";
// The words of the console's queue controls, English first and Russian second, like every other
// copy module of the panel: `studio-i18n.js` spreads this catalogue into the one table. They are
// the names of the buttons a person presses on the queue block and the sentences a press leaves
// under it; the block's own lines are `desk-copy.js` and the status words `desk-status-copy.js`. A
// refusal is said in the words of the refusal vocabulary (`error.<code>`), never here, and a
// message carries a name or a number as a named parameter, never a joined string.
export const DESK_PULT_COPY = Object.freeze({
  // -- the controls of an entry -----------------------------------------------------------
  "desk_pult.up": ["Move up", "Выше"],
  "desk_pult.down": ["Move down", "Ниже"],
  "desk_pult.withdraw": ["Remove from the queue", "Убрать из очереди"],
  // -- what a write that could not be confirmed leaves under the block ----------------------
  "desk_pult.unconfirmed": [
    "The change could not be confirmed. This is the queue the server holds.",
    "Изменение не удалось подтвердить. Здесь — очередь, как её хранит сервер."],
});
