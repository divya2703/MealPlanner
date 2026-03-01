"""Month-wise seasonal vegetables available in India."""

# Month number -> list of seasonal vegetables
SEASONAL_VEGETABLES: dict[int, list[str]] = {
    1: ["cauliflower", "green peas", "spinach", "fenugreek leaves", "carrots", "radish", "turnip", "mustard greens", "broccoli"],
    2: ["cauliflower", "green peas", "spinach", "fenugreek leaves", "carrots", "radish", "broccoli", "spring onions"],
    3: ["spinach", "fenugreek leaves", "raw mango", "spring onions", "carrots", "broccoli"],
    4: ["raw mango", "ridge gourd", "bottle gourd", "cucumber", "drumstick"],
    5: ["ridge gourd", "bottle gourd", "bitter gourd", "raw mango", "cucumber", "drumstick", "tinda"],
    6: ["ridge gourd", "bottle gourd", "bitter gourd", "okra", "tinda", "drumstick", "snake gourd"],
    7: ["okra", "ridge gourd", "bottle gourd", "bitter gourd", "corn", "tinda", "cluster beans"],
    8: ["okra", "ridge gourd", "bottle gourd", "corn", "cluster beans", "raw banana"],
    9: ["okra", "ridge gourd", "eggplant", "sweet potato", "corn", "cluster beans"],
    10: ["eggplant", "sweet potato", "cauliflower", "green peas", "beans", "capsicum"],
    11: ["cauliflower", "green peas", "spinach", "fenugreek leaves", "carrots", "beans", "capsicum", "radish"],
    12: ["cauliflower", "green peas", "spinach", "fenugreek leaves", "carrots", "radish", "turnip", "mustard greens"],
}
