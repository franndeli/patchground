# Monthly invoice report debrief

1. How did you establish the number of rows produced by each join?
2. Which fixture distinguishes summing each line once from using DISTINCT amounts?
3. Why is a month number alone not a sufficient grouping key?
4. How do the join type and filters affect an invoice with no lines?
5. What makes text comparison safe for the supplied timestamps, and when would it stop being safe?
6. How would you investigate performance with real data before adding an index?
