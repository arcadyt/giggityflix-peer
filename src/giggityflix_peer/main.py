import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel

from giggityflix_peer.config import config
from giggityflix_peer.peer_app import peer_app
from giggityflix_peer.utils.logging import setup_logging

# Create CLI app
app = typer.Typer(
    name="giggityflix_peer-peer",
    help="Peer service for Giggityflix media streaming platform",
    add_completion=False
)

console = Console()
logger = logging.getLogger(__name__)


def print_welcome_message():
    """Print a welcome message with a logo."""
    message = """
[bold cyan]Giggityflix Peer Service[/bold cyan]

[italic]Stream your local media files across your network[/italic]

Peer ID: {peer_id}
Version: 0.1.0
    """.format(peer_id=peer_app.peer_id)
    
    console.print(Panel(message, title="Welcome", expand=False))


@app.callback()
def callback():
    """Giggityflix Peer Service."""
    # Set up logging
    setup_logging()


@app.command()
def start(
    media_dirs: Optional[List[str]] = typer.Option(
        None, "--media-dir", "-m", help="Directories to scan for media files (comma-separated)"
    ),
    edge_address: Optional[str] = typer.Option(
        None, "--edge-address", "-e", help="Address of the Edge Service"
    ),
    peer_id: Optional[str] = typer.Option(
        None, "--peer-id", "-p", help="Unique identifier for this peer"
    ),
    data_dir: Optional[Path] = typer.Option(
        None, "--data-dir", "-d", help="Directory for peer data"
    ),
    scan_interval: Optional[int] = typer.Option(
        None, "--scan-interval", "-s", help="Interval between media scans in minutes"
    ),
):
    """Start the peer service."""
    # Override config with command line arguments
    if media_dirs:
        config.scanner.media_dirs = media_dirs
    
    if edge_address:
        config.grpc.edge_address = edge_address
    
    if peer_id:
        config.peer.peer_id = peer_id
    
    if data_dir:
        config.peer.data_dir = str(data_dir)
    
    if scan_interval:
        config.scanner.scan_interval_minutes = scan_interval
    
    # Print welcome message
    print_welcome_message()
    
    # Print configuration
    print("[bold]Configuration:[/bold]")
    print(f"  Media directories: {', '.join(config.scanner.media_dirs) or 'None'}")
    print(f"  Edge address: {config.grpc.edge_address}")
    print(f"  Data directory: {config.peer.data_dir}")
    print(f"  Scan interval: {config.scanner.scan_interval_minutes} minutes")
    print("")
    
    # Check if any media directories are configured
    if not config.scanner.media_dirs:
        print("[bold red]Error:[/bold red] No media directories configured!")
        print("Please specify at least one media directory using the --media-dir option")
        print("or set the MEDIA_DIRS environment variable")
        return
    
    # Run the peer application
    try:
        asyncio.run(_run_peer_app())
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        logger.error(f"Error running peer application: {e}", exc_info=True)
        print(f"[bold red]Error:[/bold red] {e}")


@app.command()
def scan():
    """Trigger a media scan."""
    print("Triggering media scan...")
    asyncio.run(_scan_media())


@app.command()
def status():
    """Show the status of the peer service."""
    # This is just a placeholder
    print("[bold]Peer Service Status:[/bold]")
    print("Not implemented yet")


async def _run_peer_app():
    """Run the peer application."""
    await peer_app.start()
    await peer_app.wait_for_stop()


async def _scan_media():
    """Trigger a media scan."""
    # Start the peer app if not running
    if not peer_app.is_running():
        await peer_app.start()
    
    # Trigger a scan
    await peer_app.scan_media()
    
    # Stop the peer app
    await peer_app.stop()


if __name__ == "__main__":
    app()
