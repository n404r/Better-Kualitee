# Kualitee Management Tool

A **modular CLI tool** for automating Kualitee test execution and defect management from the terminal.

---

## Features

* Execute test cycles with attachments
* Manage defects with bulk updates
* Modular architecture - easy to extend

---

## Installation

1. **Clone the repository**

```bash
git clone https://github.com/n404r/Better-Kualitee
cd Better-Kualitee
```

2. **Install dependencies**

```bash
pip install requests rich
```

3. **Create `config.json`**

```json
{
  "token": "YOUR_KUALITEE_API_TOKEN",
  "project_id": 27433
}
```

---

## Usage

Run the tool:

```bash
python main.py
```

Select from menu:
1. Test Cycle Management
2. Defect Management
0. Exit

---

## Adding New Modules

Want to add a feature? Follow these steps:

### 1. Create your module file

Create `modules/your_module.py`:

```python
def run_your_module():
    """Entry point for your module."""
    print("Your module logic here")
```

### 2. Update package init

Edit `modules/__init__.py`:

```python
__all__ = ['defect', 'test_cycle', 'your_module']
```

### 3. Add to main menu

Edit `main.py` - add your option:

```python
console.print("3. Your Module Name")

# In the choice handler:
elif choice == 3:
    from modules import your_module
    your_module.run_your_module()
```

That's it! Your new module is integrated.

---

## Project Structure

```
main.py                 # Entry point
config.json             # Configuration
modules/
  ├── defect.py         # Defect management
  └── test_cycle.py     # Test cycle management
```

---

## Author

**Nischay Raj**
