# This module tests the FFmpeg filter construction used by video_compare(), ensuring that temporal offsets and overlapping intervals are applied consistently to VMAF, PSNR, and SSIM calculations.
import subprocess
import quality_metrics


def test_video_compare_applies_offset_to_all_metrics(monkeypatch):
    """
    All three metrics must use the same temporally trimmed video streams.
    """

    monkeypatch.setattr(
        quality_metrics,
        "get_video_metadata",
        lambda path: {"duration": 10.0},
    )
    monkeypatch.setattr(
        quality_metrics,
        "get_video_duration",
        lambda path: 10.0,
    )
    monkeypatch.setattr(
        quality_metrics,
        "get_video_r_fps",
        lambda path: 30.0,
    )
    monkeypatch.setattr(
        quality_metrics,
        "get_overlap_interval",
        lambda reference_duration, distorted_duration, offset: (
            0.0, 1.0, 9.0
        ),
    )

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        raise subprocess.TimeoutExpired(command, timeout=300)

    monkeypatch.setattr(quality_metrics.subprocess, "run", fake_run)

    try:
        quality_metrics.video_compare("reference.mp4", "distorted.mp4", offset=1.0)
    except RuntimeError as error:
        assert "timed out" in str(error)
    else:
        raise AssertionError("expected the mocked FFmpeg timeout")

    command = captured["command"]
    filter_complex = command[command.index("-filter_complex") + 1]

    assert "[dist]split=3[dist_vmaf][dist_psnr][dist_ssim]" in filter_complex
    assert "[ref]split=3[ref_vmaf][ref_psnr][ref_ssim]" in filter_complex

    assert "[dist_vmaf][ref_vmaf]libvmaf=" in filter_complex
    assert "[dist_psnr][ref_psnr]psnr=" in filter_complex
    assert "[dist_ssim][ref_ssim]ssim=" in filter_complex
