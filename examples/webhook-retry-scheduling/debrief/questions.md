# Debrief

- Which transitions are terminal, and when should attempts increment?
- How did you prove one failure cannot starve unrelated due deliveries?
- Why calculate backoff from the drain time rather than the previous due time?
- Which retry-after values need special treatment in Python's type system?
- Why is repeated-ID handling not an exactly-once delivery guarantee?
- What would crash recovery and multiple workers require that this queue does not provide?
