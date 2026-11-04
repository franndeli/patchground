# Debrief

1. What reproduction distinguished an ownership bug from a validation bug?
2. Where did references cross the saved/draft boundary, and why was a top-level copy insufficient?
3. Which checks would catch copying the array but still sharing its items?
4. Why must the save result be independent even when the draft was already copied?
5. What would change if items contained nested metadata? Where should that schema decision live?
6. What would persistence and concurrent editors add that this exercise deliberately does not claim?
