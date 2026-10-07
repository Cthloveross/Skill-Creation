# Dataset field notes (TravelPlanner-style CSVs)

Column names are discovered at runtime by `travel_db.find_col`, so treat the
names below as expected conventions, not guarantees.

## accommodations/clean_accommodations_2022.csv
- Typical columns: `NAME`, `price`, `room type`, `house_rules`, `minimum nights`,
  `maximum occupancy`, `review rate number`, `city`.
- Pet-friendly rule: a row is pet-friendly iff its `house_rules` text does NOT
  contain `No pets` (case-insensitive). Other rules (no smoking, no parties) do
  not disqualify.
- Party capacity: `maximum occupancy >= people`.
- Minimum-stay: `minimum nights <= nights actually booked` (2 here).
- `price` is per night per room.

## restaurants/clean_restaurant_2022.csv
- Typical columns: `Name`, `Average Cost`, `Cuisines`, `Aggregate Rating`, `City`.
- `Cuisines` may list several cuisines; membership is a case-insensitive substring
  check. Cuisine is a *preference*, never a hard reject.
- Meal cost = `Average Cost * people` per meal.
- Meal output text is `Name, City` so both the record and its city resolve.
- No restaurant is reused across the trip.

## attractions/attractions.csv
- Typical columns: `Name`, `Latitude`, `Longitude`, `Address`, `Phone`,
  `Website`, `City`.
- Attraction output lists names separated by `;` and ends with `;`.
- No attraction is reused across the trip.

## googleDistanceMatrix/distance.csv
- Typical columns: `source`, `destination`, `cost`, `duration`, `distance`.
- Matrix may be directional/incomplete; validate the exact requested direction.
- Self-driving cost model used here: `distance_km * 0.05` per car, one car per
  5 people (`ceil(people/5)`), rounded to an integer. The `cost` column is left
  untouched because it reflects a different (taxi) model.

## background/
- `citySet_with_states.txt`: `City<TAB>State` per line (used to find cities in a
  requested state).

## Flights
- The flights CSV is intentionally never read: the task forbids flights, so every
  transition is `Self-driving: from A to B` and non-travel days use `-`.

## Day pattern
- origin -> city1 -> city2 -> ... -> cityK -> origin.
- Per city: a travel-in day (sleep in that city) and a stay day => 2 nights each.
- Final day drives back to origin with no overnight (accommodation `-`).
- This yields `2*K + 1` days (K=3 -> 7). If the requested day count differs, stay
  days in the last city are padded/trimmed to match exactly.
- Travel-day meals: breakfast in the leg origin, dinner in the leg destination,
  lunch `-`; attractions `-` on travel days (long drive). Stay days fill all three
  meals and up to two attractions in that city.
