"""Animation layer: presets resolve cleanly, revisions are params, outputs are valid. No Blender needed."""
import xml.etree.ElementTree as ET

import pytest

from asset_agent import anim


@pytest.mark.parametrize("name", list(anim.presets()))
def test_presets_are_clean(name):
    d = anim.resolve({"preset": name})
    stats, warns = anim.check(d)
    assert warns == []
    assert abs(stats["low"]) < 0.02  # feet on the floor: neither sinking nor hovering


def test_rig_matches_studio():
    """Part centres of the run at 0.2 s, measured on Studio's default R15 (relative to the root, +3 studs)."""
    studio = {"RightHand": (1.67, 3.13, -1.39), "LeftUpperLeg": (-0.49, 1.63, -0.1), "Head": (0.02, 4.66, -0.7),
              "UpperTorso": (0.01, 3.29, -0.33)}
    d = anim.resolve({"preset": "run"})
    world = anim.solve(anim.pose_at(d, 0.2 / d["length"], ground=False))
    for part, want in studio.items():
        r, t = world[part]
        got = [a + b for a, b in zip(anim._mv(r, anim.RIG[part][2]), t)]
        assert max(abs(a - b) for a, b in zip(got, want)) < 0.15, part


def test_mirror_opposite_is_half_a_cycle_later():
    d = anim.resolve({"preset": "walk"})
    for u in (0.0, 0.2, 0.35):
        right = anim.pose_at(d, u, ground=False)["RightUpperLeg"][3]
        left = anim.pose_at(d, u + 0.5, ground=False)["LeftUpperLeg"][3]
        assert right == pytest.approx(left)


def test_knobs_scale_motion_not_rest_pose():
    base = anim.resolve({"preset": "run"})
    big = anim.resolve({"preset": "run", "params": {"arms": 2.0, "speed": 2.0}})
    assert big["length"] == pytest.approx(base["length"] / 2)
    b0 = anim.pose_at(base, 0.5, ground=False)["RightUpperArm"][3]
    b1 = anim.pose_at(big, 0.5, ground=False)["RightUpperArm"][3]
    o = base["tracks"]["RightUpperArm"]["rx"]["o"]
    assert b1 - o == pytest.approx(2 * (b0 - o))


def test_plant_keeps_crouching_feet_on_the_floor():
    d = anim.resolve({"preset": "idle", "tracks": {"LowerTorso": {"y": -0.6}}})
    pose = anim.pose_at(d, 0)
    assert abs(anim.lowest(pose)) < 0.01
    assert pose["RightLowerLeg"][3] < -40  # knees bent to make the crouch


def test_bad_specs_fail_without_saving(tmp_path):
    a = anim.Animation(tmp_path / "x")
    with pytest.raises(KeyError, match="unknown joint"):
        a.update(preset="run", tracks={"Tail": {"rx": 3}})
    assert not (tmp_path / "x" / "anim.json").exists()
    a.update(preset="run")
    with pytest.raises(KeyError, match="unknown param"):
        a.update(params={"swagger": 2})
    assert anim.Animation(tmp_path / "x").m["version"] == 1


def test_revision_rollback_and_export(tmp_path):
    a = anim.Animation(tmp_path / "hero_run")
    l1 = a.update(preset="run")
    assert "v1" in l1 and "loop" in l1
    l2 = a.update(params={"speed": 1.4, "arms": 1.3})
    assert "v2" in l2 and "0.50s" in l2
    root = ET.parse(tmp_path / "hero_run" / "export" / "hero_run.rbxmx").getroot()
    kfs = root.find("Item")
    assert kfs.get("class") == "KeyframeSequence"
    keyframes = kfs.findall("Item")
    assert len(keyframes) == 16 and all(k.get("class") == "Keyframe" for k in keyframes)
    assert (tmp_path / "hero_run" / "export" / "versions" / "v1.rbxmx").exists()
    l3 = a.rollback(1)
    assert "v3" in l3 and "0.70s" in l3 and a.history().splitlines()[-1] == "v3: rollback to v1"
    assert (tmp_path / "hero_run" / "preview.png").stat().st_size > 1000


def test_loop_keys_that_dont_meet_are_flagged():
    d = anim.resolve({"preset": "idle", "tracks": {"Head": {"ry": {"keys": [[0, 0], [1, 30]]}}}})
    assert any("pops" in w for w in anim.check(d)[1])


def test_studio_script_mentions_every_frame():
    d = anim.resolve({"preset": "jump"})
    code = anim.studio_script("j", d)
    assert "KeyframeSequenceProvider" in code and "Enum.AnimationPriority.Action" in code
    assert code.count("],[") >= len(anim.samples(d)) - 1
