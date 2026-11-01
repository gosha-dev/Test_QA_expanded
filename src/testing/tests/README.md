# Running the tests

Run these commands from the repository root in Windows PowerShell.

## Prepare the environment

Create and activate a virtual environment, then install the project dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Test types

This folder contains two kinds of tests:

- **`test_ammeters.py`** runs integration tests against the ammeter simulators. Its fixture starts `main.py`, waits for the simulators to start, and stops the process after the tests. The tests request measurements and check sampling behavior.
- **`test_infra_unitests.py`** checks the testing infrastructure itself, including analysis, result storage, and visualization logic. These unit tests do not start the ammeter simulators.

### Known simulator limitation

`test_ammeter_sampling_performance[greenlee-5000]` attempts to validate Greenlee sampling at 5 kHz. The current simulator cannot reliably sustain this rate, so request latency affects the measured intervals and jitter. The test may therefore exceed its timing tolerances; this limitation does not by itself indicate a problem with lower-frequency sampling.

## Run tests

Run every test in this folder:

```powershell
pytest.exe .\src\testing\tests\ -v --tb=no
```

Run only the infrastructure unit tests:

```powershell
pytest.exe .\src\testing\tests\test_infra_unitests.py
```

Run only the ammeter integration tests:

```powershell
pytest.exe .\src\testing\tests\test_ammeters.py -v --tb=no
```
