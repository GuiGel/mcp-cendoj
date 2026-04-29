from unittest.mock import patch

from mcp_cendoj import main


def test_main_runs() -> None:
    with patch('mcp_cendoj.app.run') as mock_run:
        main()
        mock_run.assert_called_once()
