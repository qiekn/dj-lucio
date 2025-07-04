import os

import cv2

template_dir = r"..\assets\templates"

coords = {
    "elimination": [751, 779, 833, 975],
    "assist": [751, 779, 833, 975],
    "save": [751, 779, 729, 923],
    "killcam": [89, 107, 41, 69],
    "death_spec": [66, 86, 1416, 1574],
    "being_beamed": [763, 807, 461, 508],
    "being_orbed": [760, 800, 465, 619],
    "hacked": [858, 882, 172, 197],
    "overtime": [37, 57, 903, 1016],
    "baptiste_weapon": [963, 974, 1722, 1747],
    "brigitte_weapon": [958, 974, 1697, 1723],
    "kiriko_weapon": [964, 969, 1682, 1719],
    "lucio_weapon": [958, 968, 1702, 1742],
    "lucio_heal": [668, 698, 796, 824],
    "lucio_speed": [668, 698, 1093, 1126],
    "mercy_staff": [958, 974, 1768, 1789],
    "mercy_pistol": [946, 958, 1669, 1709],
    "mercy_pistol_ult": [945, 960, 1669, 1697],
    "mercy_heal_beam": [672, 706, 807, 841],
    "mercy_damage_beam": [673, 705, 1080, 1112],
    "mercy_resurrect_cd": [920, 1000, 1570, 1655],
    "zenyatta_weapon": [966, 979, 1717, 1731],
    "zenyatta_harmony": [954, 986, 738, 762],
    "zenyatta_discord": [954, 985, 1157, 1182],
    "juno_weapon": [950, 960, 1679, 1708],
    "juno_glide_boost": [933, 964, 1428, 1461],
    "juno_pulsar_torpedoes": [940, 975, 1581, 1620],
    "juno_pulsar_torpedoes_timer": [613, 645, 447, 450],
}

print(f"{'Template':<30} {str('Crop'):>12} {str('Shape'):>12} {"Diff":>12}")
print("---------------------------------------------------------------------")

for file in os.listdir(template_dir):
    path = os.path.join(template_dir, file)
    image = cv2.imread(path)

    name = os.path.splitext(file)[0][2:]
    shape = image.shape[:2]

    top, bottom, left, right = coords[name]
    shape2 = bottom - top, right - left

    diff = shape2[0] - shape[0], shape2[1] - shape[1]

    print(f"{name:<30} {str(shape):>12} {str(shape2):>12} {str(diff):>12}")
