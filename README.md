# Wallabag reading stats.

I wanted to know how much I am reading. 
This reads all archived articles, one page at a time, until it runs out of pages.
It then reports the number of articles and minutes per week (7 days), month (30 days) and year (365 days) as well as the average reading time.

This is, curerntly very simple.
The bulk of this code was generated through [duck.ai](https://duck.ai/) using GPT-5 mini (2026-06-15.)
I have reviewd and tweaked it as necesary to get it to work as expected.

# Notes:
This does not do polite things, like caching results for future runs. 
Thus it should not be run very frequently as it will be hard ont he server.

# Potential imporvments:
[ ] Give articles read per period as a graph. (A bar chart of weeks, months and years)
[ ] Cache the resutls so that they are not so hard on the site.
[ ] Do some proper security for accepting password and secrets.
