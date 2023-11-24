# airbnbs-vs-rentals
Exploratory data visualisation of Airbnb listings and residential rental properties.

This is my first Python program. It uses Airbnb data from [Inside Airbnb](http://insideairbnb.com/get-the-data) and rental data from [Stats NZ](https://nzdotstat.stats.govt.nz/wbos/Index.aspx) to map the counts and median prices of Airbnb listings and residential rental properties.

**How to use the program:**

When using the program with the included datasets, all the user needs to do is run `main()` and follow the prompts to enter the relevant filenames, city, and their chosen filename prefix in order to get an HTML file of each map type. If desired, they could comment out certain map types they do not want.
The user can run the program with other NZ.Stat or Inside Airbnb datasets if desired; they will just need to edit the global constants to conform with the new datasets. This flexibility means that the program will work for other cities and/or time periods.

**About the ratios:**

- If both variables are equal, ratio = 0.
- If the rental variable is less than the Airbnb variable, ratio = Airbnb variable * (-1 / rental variable (+ 1 if rental variable = 0)).
- If the rental variable is greater than the Airbnb variable, ratio = rental variable * (1 / Airbnb variable (+ 1 if Airbnb variable = 0)).

This results in a ratio where, if we consider more rental properties and fewer Airbnbs to be a good thing, then a bigger value is better. For example, a ratio of 6 means there are six times as many rental properties as Airbnbs. Meanwhile, a ratio of -2 means there are two times as many Airbnbs as rental properties. I decided to keep the same logic for comparing the prices – not because I think that higher rental prices are a positive thing, but because Airbnb prices being higher than rental prices is what is threatening the rental market.
