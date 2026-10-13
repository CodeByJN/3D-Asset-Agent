"""Animation layer: presets resolve cleanly, revisions are params, outputs are valid. No Blender needed."""
import xml.etree.ElementTree as ET

import pytest

from asset_agent import anim


@pytest.mark.parametrize("name", list(anim.presets()))
def test_presets_are_clean(name):
    d = anim.resolve({"preset": name})
    stats, warns = anim.check(d)
    assert warns == []
    assert stats["low"] > -0.02  # nothing sinks into the floor
    if "airborne" not in anim.presets()[name].get("tags", []):
        assert stats["low"] < 0.02  # and grounded moves don't hover


def test_rig_matches_studio():
    """A fixed pose built with studio_script on Studio's default R15, part centres measured in the
    workspace (floor at y=0)."""
    studio = {"RightHand": (0.954, 3.46, -2.206), "RightLowerArm": (1.178, 3.443, -1.582), "Head": (-0.069, 4.829, -0.389),
              "UpperTorso": (-0.026, 3.426, -0.145), "LeftUpperLeg": (-0.533, 1.782, -0.145),
              "LeftLowerLeg": (-0.548, 1.004, -0.227), "LeftFoot": (-0.506, 0.344, 0.009)}
    d = anim.resolve({"tracks": {"UpperTorso": {"rx": -10, "ry": 20}, "Head": {"ry": 30}, "RightUpperArm": {"rx": 40, "rz": 20},
                                 "RightLowerArm": {"rx": 60}, "LeftUpperLeg": {"rx": 30}, "LeftLowerLeg": {"rx": -50},
                                 "LowerTorso": {"ry": 10}}})
    world = anim.solve(anim.pose_at(d, 0, ground=False))
    for part, want in studio.items():
        r, t = world[part]
        got = [a + b for a, b in zip(anim._mv(r, anim.RIG[part][2]), t)]
        assert max(abs(a - b) for a, b in zip(got, want)) < 0.05, (part, got)


def test_mirror_opposite_is_half_a_cycle_later():
    d = anim.resolve({"preset": "walk"})
    for u in (0.0, 0.2, 0.35):
        right = anim.pose_at(d, u, ground=False)["RightUpperLeg"][3]
        left = anim.pose_at(d, u + 0.5, ground=False)["LeftUpperLeg"][3]
        assert right == pytest.approx(left)


def test_knobs_scale_motion_not_rest_pose():
    base = anim.resolve({"preset": "run", "params": {"overlap": 0}})
    big = anim.resolve({"preset": "run", "params": {"arms": 2.0, "speed": 2.0, "overlap": 0}})
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
    assert "v2" in l2 and "0.47s" in l2
    root = ET.parse(tmp_path / "hero_run" / "export" / "hero_run.rbxmx").getroot()
    kfs = root.find("Item")
    assert kfs.get("class") == "KeyframeSequence"
    keyframes = kfs.findall("Item")
    assert len(keyframes) == 15 and all(k.get("class") == "Keyframe" for k in keyframes)
    assert (tmp_path / "hero_run" / "export" / "versions" / "v1.rbxmx").exists()
    l3 = a.rollback(1)
    assert "v3" in l3 and "0.66s" in l3 and a.history().splitlines()[-1] == "v3: rollback to v1"
    assert (tmp_path / "hero_run" / "preview.png").stat().st_size > 1000


def test_ik_reaches_and_mirrors():
    d = anim.resolve({"preset": "idle", "params": {"overlap": 0}, "tracks": {
        "RightHand": {"ik": [0.4, 4.2, -1.2]}, "LeftHand": {"ik": [-0.4, 4.2, -1.2]}}})
    world = anim.solve(anim.pose_at(d, 0))
    for end, want in (("RightHand", (0.4, 4.2, -1.2)), ("LeftHand", (-0.4, 4.2, -1.2))):
        r, t = world[end]
        got = [a + b for a, b in zip(anim._mv(r, anim.RIG[end][1]), t)]
        assert max(abs(a - b) for a, b in zip(got, want)) < 0.12, (end, got)
    feet = anim.resolve({"preset": "wave"})["tracks"]
    assert feet["LeftFoot"]["ik"][0] == -feet["RightFoot"]["ik"][0]


def test_splines_flow_through_keys():
    keys = [[0, 0], [0.5, 10], [1, 0]]
    assert anim._keys(keys, 0.5, False) == 10
    # moving through the middle key, not stopping on it (smoothstep would come to rest there)
    before, after = anim._keys([[0, 0], [0.5, 10], [1, 20]], 0.49, False), anim._keys([[0, 0], [0.5, 10], [1, 20]], 0.51, False)
    assert after - before > 0.3


def test_loop_keys_that_dont_meet_are_flagged():
    d = anim.resolve({"preset": "idle", "tracks": {"Head": {"ry": {"keys": [[0, 0], [1, 30]]}}}})
    assert any("pops" in w for w in anim.check(d)[1])


def test_studio_script_mentions_every_frame():
    d = anim.resolve({"preset": "jump"})
    code = anim.studio_script("j", d)
    assert "KeyframeSequenceProvider" in code and "Enum.AnimationPriority.Action" in code
    assert code.count("],[") >= len(anim.samples(d)) - 1


@pytest.mark.parametrize("name", list(anim.presets()))
def test_no_joint_pops(name):
    """A joint never jumps in one frame (the leg glitches: knee flips, foot snaps at contact)."""
    assert not [w for w in anim.check(anim.resolve({"preset": name}))[1] if "pops" in w]


def test_pop_detector_catches_a_flip():
    d = anim.resolve({"preset": "idle", "tracks": {"Head": {"ry": {"keys": [[0, 0], [0.5, 0], [0.52, 170], [1, 170]], "ease": "linear"}}},
                      "params": {"loop": False}})
    assert any("Head pops" in w for w in anim.check(d)[1])
