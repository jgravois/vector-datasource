#cliff in Yosemite
# https://www.openstreetmap.org/way/291684864
assert_has_feature(
    13, 1374, 3166, "earth",
    {"kind": "cliff", "id": 291684864,
     "sort_key": 227})

#arete in Yosemite
# https://www.openstreetmap.org/way/375271242
assert_has_feature(
    13, 1379, 3164, "earth",
    {"kind": "arete", "id": 375271242,
     "sort_key": 228})

#ridge with name in Santa Cruz Mountains, California
# https://www.openstreetmap.org/way/115675159
assert_has_feature(
    13, 1317, 3182, "earth",
    {"kind": "ridge", "id": 115675159,
     "name": "Castle Rock Ridge", "label_placement": 'yes'})

#valley with name in Yosemite
# https://www.openstreetmap.org/way/407467016
assert_has_feature(
    13, 1381, 3164, "earth",
    {"kind": "valley", "id": 407467016,
     "name": "Lyell Canyon", "label_placement": 'yes'})
