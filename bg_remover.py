from pathlib import Path
from rembg import remove


def remove_image_background(input_path, output_path):
    """
    Remove the background from an image.

    Args:
        input_path: Path to the original image.
        output_path: Path where the transparent PNG will be saved.
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input image not found: {input_path}"
        )

    # Read original image
    with open(input_path, "rb") as input_file:
        input_image = input_file.read()

    # Remove background
    output_image = remove(input_image)

    # Make sure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save transparent image
    with open(output_path, "wb") as output_file:
        output_file.write(output_image)

    print(f"Background removed: {output_path}")


if __name__ == "__main__":
    remove_image_background(
        "imgs/me.jpg",
        "imgs/profile_no_bg.png"
    )