In this tutorial you will set up a Frappe development bench, create a site, install FoaMES on it, and check that it is running. At the end you will have a site you can use for the other tutorials.

**You need:** a Linux or macOS machine (or WSL2 on Windows) where you can install software, about 4 GB of free memory, and an internet connection. You do **not** need ERPNext.

> If you would rather not install Frappe's prerequisites on your machine, the repository has a [Docker dev bench](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/dev-bench.md) that runs the same setup in containers. Follow that page, then continue from step 4 below.

## 1. Install Frappe's prerequisites

FoaMES runs on Frappe v15 or v16. Follow Frappe's own [installation guide](https://docs.frappe.io/framework/user/en/installation) for your platform. It installs Python 3.10 or later, Node.js, Yarn, MariaDB, Redis and the `bench` command. When it is done, this should print a version:

```bash
bench --version
```

## 2. Create a bench

A bench is a folder that holds the Frappe framework, your apps and your sites.

```bash
bench init --frappe-branch version-15 frappe-bench
cd frappe-bench
```

Use `version-16` instead if you prefer; both are tested in CI.

## 3. Get FoaMES and create a site

```bash
bench get-app https://github.com/CLR-Technologies-Inc/foames
bench new-site foames.localhost --admin-password admin
bench --site foames.localhost install-app foames
```

Installing creates the FoaMES roles (Engineer, Operator, Quality, Supervisor, Maintenance and Integration), five andon call types, the workspaces and the reports. Nothing asks you for an ERP.

## 4. Turn the scheduler on and start the bench

FoaMES uses the Frappe scheduler for its daily OEE, its hourly suggestion rules and its five-minute staleness check.

```bash
bench --site foames.localhost enable-scheduler
bench start
```

Leave `bench start` running in its own terminal. Open <http://foames.localhost:8000> and log in as `Administrator` with the password `admin`.

## 5. Give yourself the FoaMES roles

1. In the desk, open **User** and then your user (Administrator is fine on a dev site).
2. Under **Roles**, tick **FoaMES Engineer** and **FoaMES Operator**.
3. Save.

## 6. Check that it works

1. Type **Floor View** in the search bar, or open <http://foames.localhost:8000/app/floor-view>. With no machines yet, it says so.
2. Open **FoaMES Settings**. **Default ERP System** is empty, which means FoaMES is running without an ERP. Leave it that way for now.
3. Open the **FoaMES Supervisor** workspace from the sidebar. You see empty number cards and charts; they fill in once machines report.

You now have a working FoaMES site. Next, give it a machine: [Tutorial 2: Your first machine and OEE](Tutorial-2-Your-first-machine-and-OEE).

## If something went wrong

- **`install-app` fails on a Frappe version check.** FoaMES accepts Frappe v15 and v16 only, not the `develop` branch.
- **The Floor View says you are not permitted.** Your user needs FoaMES Engineer, Operator or Quality, or System Manager.
- **Nothing happens on a schedule.** Run `bench --site foames.localhost scheduler status`; on a dev bench with `developer_mode` on, the scheduler is often paused.

The full installation guide, including production benches, Frappe Cloud, updates and uninstalling, is [docs/installation.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/installation.md).
