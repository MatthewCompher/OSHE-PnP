# Loading Tape

1. Cut the tape end square, just before a full pocket.
2. Peel back about 5 cm of the clear cover tape.
3. Thread the tape into the feeder from the reel side, pockets up, sprocket holes on the lever side,
   until the first full pocket sits just past the pick window.
4. Route the peeled cover tape back over the top so it can't fall into the pick window.
5. `FEEDER_TOGGLE SLOT=1 COUNT=2` (Mainsail console): the tape should advance two pockets
   cleanly, with the lever catching a sprocket hole each time.
6. Check a part sits in the pick window. If the window is empty, feed once more.

!!! tip "Keep the reel turning freely"
    The servo is weak: a reel that drags or tape that catches on its way in is the most common
    cause of short feeds.

When the tape type or feeder position changed, re-teach the pick spot: [Teaching a Feeder](teaching.md).
