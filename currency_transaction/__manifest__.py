{
    "name": "Currency Transaction",
    "description": "Manage cash transactions with multi-currency support, reconciliation, and transfer account handling.",
    "summary": "Cash currency transaction management and reconciliation",
    "author": "Ammar Barwary",
    "website": "",
    "category": "Accounting",
    "license": "LGPL-3",
    "version": "19.0.1.0.0",
    "data": [
        "views/journal_cash_list.xml",
        "views/currency_transaction_menu.xml",
        "data/mail_subtypes.xml",
        "security/ir.model.access.csv",
        "report/currency_transaction_reports.xml",
        "report/currency_transaction_report_templates.xml"
    ],
    "images": [
        "main_screenshot.jpg"
    ],
    "depends": ["account", "mail"],
    "application": True,
    "installable": True,
    "currency": "USD",
    "price": "30.00"
}
