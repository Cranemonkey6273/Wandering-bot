from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


INFECTED_PREFIXES = ("ZmbM_", "ZmbF_")
EXPLOSIVE_CHANCES = (
    ("FlashGrenade", "0.05"),
    ("Grenade_ChemGas", "0.05"),
)


def parse_xml(path: Path) -> ET.ElementTree:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(path, parser=parser)


def is_infected(type_node: ET.Element) -> bool:
    name = type_node.get("name", "")
    return name.startswith(INFECTED_PREFIXES)


def ensure_ruined_damage(root: ET.Element, class_name: str) -> None:
    matching = [node for node in root.findall("type") if node.get("name") == class_name]
    if len(matching) > 1:
        raise ValueError(f"Duplicate cfgspawnabletypes record for {class_name}")

    if matching:
        type_node = matching[0]
    else:
        type_node = ET.Element("type", {"name": class_name})
        flash_index = next(
            (index for index, node in enumerate(root) if node.tag == "type" and node.get("name") == "FlashGrenade"),
            len(root) - 1,
        )
        root.insert(flash_index + 1, type_node)

    damage_nodes = type_node.findall("damage")
    if len(damage_nodes) > 1:
        raise ValueError(f"Multiple damage records for {class_name}")
    damage = damage_nodes[0] if damage_nodes else ET.SubElement(type_node, "damage")
    damage.set("min", "1.0")
    damage.set("max", "1.0")


def validate_types(types_path: Path) -> None:
    root = parse_xml(types_path).getroot()
    if root.tag != "types":
        raise ValueError(f"Expected types root, got {root.tag}")

    for class_name, _chance in EXPLOSIVE_CHANCES:
        matching = [node for node in root.findall("type") if node.get("name") == class_name]
        if len(matching) != 1:
            raise ValueError(f"Expected exactly one types.xml record for {class_name}")
        nominal = matching[0].findtext("nominal")
        minimum = matching[0].findtext("min")
        if nominal != "0" or minimum != "0":
            raise ValueError(
                f"{class_name} should remain nominal 0/min 0 so ruined grenades do not spawn as ordinary loot"
            )


def transform_spawnabletypes(source: Path, destination: Path) -> int:
    tree = parse_xml(source)
    root = tree.getroot()
    if root.tag != "spawnabletypes":
        raise ValueError(f"Expected spawnabletypes root, got {root.tag}")

    infected_nodes = [node for node in root.findall("type") if is_infected(node)]
    if not infected_nodes:
        raise ValueError("No infected cfgspawnabletypes records found")

    for infected in infected_nodes:
        for class_name, chance in EXPLOSIVE_CHANCES:
            existing = infected.findall(f'.//item[@name="{class_name}"]')
            if existing:
                raise ValueError(
                    f'{infected.get("name")} already contains {class_name}; refusing to create a duplicate cargo item'
                )
            cargo = ET.SubElement(infected, "cargo", {"chance": chance})
            ET.SubElement(cargo, "item", {"name": class_name, "chance": "1.00"})

    for class_name, _chance in EXPLOSIVE_CHANCES:
        ensure_ruined_damage(root, class_name)

    ET.indent(tree, space="    ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(destination, encoding="utf-8", xml_declaration=True, short_empty_elements=True)

    check_root = ET.parse(destination).getroot()
    output_infected = [node for node in check_root.findall("type") if is_infected(node)]
    if len(output_infected) != len(infected_nodes):
        raise ValueError("Infected count changed during generation")
    for infected in output_infected:
        for class_name, chance in EXPLOSIVE_CHANCES:
            items = infected.findall(f'./cargo[@chance="{chance}"]/item[@name="{class_name}"]')
            if len(items) != 1 or items[0].get("chance") != "1.00":
                raise ValueError(f'Generated cargo validation failed for {infected.get("name")} / {class_name}')
    return len(infected_nodes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a validated explosive-infected DayZ package")
    parser.add_argument("--spawnabletypes", required=True, type=Path)
    parser.add_argument("--types", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    validate_types(args.types)
    infected_count = transform_spawnabletypes(args.spawnabletypes, args.output / "cfgspawnabletypes.xml")
    shutil.copyfile(args.types, args.output / "types.xml")
    print(f"Generated {args.output} for {infected_count} infected records")


if __name__ == "__main__":
    main()
