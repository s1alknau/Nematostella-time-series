"""
Quick API verification for Zarr V3 sharding.
Tests both common API variants and reports which one works.

Run from imswitch21 env:
    python scripts/test_zarr_sharding_api.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import zarr

print(f"Zarr version: {zarr.__version__}")
print(f"numpy version: {np.__version__}")
print()


def test_variant(name: str, create_fn) -> bool:
    """Run a sharding API variant and report success/failure."""
    print(f"--- Variant: {name} ---")
    tmpdir = Path(tempfile.mkdtemp(prefix="zarr_shard_test_"))
    try:
        store_path = tmpdir / "test.zarr"

        # Open store
        if hasattr(zarr.storage, "LocalStore"):
            store = zarr.storage.LocalStore(str(store_path))
        else:
            store = zarr.DirectoryStore(str(store_path))
        root = zarr.open_group(store=store, mode="w")
        root.require_group("images")

        # Create array via the variant
        H, W = 256, 256
        N = 200  # enough to span multiple shards if shard size is 50
        dtype = np.uint16
        arr = create_fn(root["images"], shape=(N, H, W), dtype=dtype, H=H, W=W)
        print(
            f"  ✓ create_array succeeded — shape={arr.shape}, chunks={getattr(arr, 'chunks', None)}"
        )

        # Write 150 frames sequentially (covers 3 shards if shard_size=50)
        rng = np.random.default_rng(42)
        for i in range(150):
            arr[i] = rng.integers(0, 4096, size=(H, W), dtype=dtype)
        print("  ✓ 150 sequential writes succeeded")

        # Read back a few frames
        sample = arr[42]
        assert sample.shape == (H, W)
        assert sample.dtype == dtype
        print(f"  ✓ Read back frame 42 — shape={sample.shape}, dtype={sample.dtype}")

        # Count files in the chunks/shards subdir to verify shard count
        chunks_dirs = list(store_path.rglob("c"))
        for d in chunks_dirs:
            if d.is_dir():
                files = list(d.rglob("*"))
                file_count = sum(1 for f in files if f.is_file())
                print(f"  ✓ {d.relative_to(store_path)}: {file_count} chunk/shard files")
                break
        else:
            # V2 layout: chunk files in array dir directly
            arr_dir = store_path / "images" / "frames"
            if arr_dir.exists():
                file_count = sum(
                    1 for f in arr_dir.iterdir() if f.is_file() and not f.name.startswith(".")
                )
                print(f"  ✓ {arr_dir.relative_to(store_path)}: {file_count} chunk files")

        print("  ✓ VARIANT PASSED\n")
        return True

    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}\n")
        return False
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


# ============================================================
# Variant A: high-level `shards=` parameter on create_array
# ============================================================
def variant_a(group, shape, dtype, H, W):
    return group.create_array(
        name="frames",
        shape=shape,
        dtype=dtype,
        chunks=(1, H, W),
        shards=(50, H, W),
    )


# ============================================================
# Variant B: ShardingCodec explicit
# ============================================================
def variant_b(group, shape, dtype, H, W):
    from zarr.codecs import BytesCodec, ShardingCodec

    return group.create_array(
        name="frames",
        shape=shape,
        dtype=dtype,
        chunks=(50, H, W),
        codecs=[
            ShardingCodec(
                chunk_shape=(1, H, W),
                codecs=[BytesCodec()],
            ),
        ],
    )


# ============================================================
# Variant C: plain create_dataset (no sharding, baseline)
# ============================================================
def variant_c(group, shape, dtype, H, W):
    return group.create_dataset(
        "frames",
        shape=shape,
        chunks=(50, H, W),
        dtype=dtype,
    )


results = {}
results["A (shards= param)"] = test_variant("A (shards= param)", variant_a)
results["B (ShardingCodec)"] = test_variant("B (ShardingCodec)", variant_b)
results["C (no sharding baseline)"] = test_variant("C (no sharding baseline)", variant_c)

print("=" * 60)
print("SUMMARY")
print("=" * 60)
for name, ok in results.items():
    status = "✓ WORKS" if ok else "✗ fails"
    print(f"  {status:10}  {name}")
print()

if results["A (shards= param)"]:
    print("→ Will use VARIANT A in production code (cleanest API)")
elif results["B (ShardingCodec)"]:
    print("→ Will use VARIANT B in production code (explicit codecs)")
elif results["C (no sharding baseline)"]:
    print("→ Sharding not available — falling back to plain chunks")
else:
    print("→ ALL VARIANTS FAILED — environment is broken, revert Zarr version")
    sys.exit(1)
