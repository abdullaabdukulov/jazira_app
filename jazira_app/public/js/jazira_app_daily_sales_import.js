frappe.ui.form.on('Jazira App Daily Sales Import', {
    
    refresh: function(frm) {
        frm.trigger('setup_buttons');
        frm.trigger('setup_realtime');
        frm.trigger('show_status_indicator');
        frm.trigger('set_warehouse_filter');
    },
    
    company: function(frm) {
        frm.set_value('source_warehouse', '');
        frm.trigger('set_warehouse_filter');
    },
    
    source_warehouse: function(frm) {
        frm.trigger('validate_prerequisites');
    },
    
    posting_date: function(frm) {
        frm.trigger('validate_prerequisites');
    },
    
    excel_file: function(frm) {
        if (frm.doc.excel_file) {
            frm.trigger('on_excel_uploaded');
        }
    },
    
    set_warehouse_filter: function(frm) {
        frm.set_query('source_warehouse', function() {
            return {
                filters: {
                    'company': frm.doc.company || '',
                    'is_group': 0
                }
            };
        });
    },
    
    validate_prerequisites: function(frm) {
        let valid = frm.doc.company && frm.doc.source_warehouse && frm.doc.posting_date;
        
        if (!valid) {
            frm.set_df_property('excel_file', 'read_only', 1);
            frm.set_df_property('excel_file', 'description', 
                '<span style="color: red;">Avval Company, Warehouse va Posting Date tanlang!</span>');
        } else {
            frm.set_df_property('excel_file', 'read_only', 0);
            frm.set_df_property('excel_file', 'description', 
                'POS hisoboti Excel fayli (.xlsx)');
        }
    },
    
    on_excel_uploaded: function(frm) {
        if (frm.doc.status !== 'Draft') {
            frappe.msgprint(__('Import allaqachon bajarilgan'));
            return;
        }
        
        frm.save().then(() => {
            frm.trigger('show_preview');
        });
    },
    
    setup_buttons: function(frm) {
        frm.clear_custom_buttons();
        
        if (frm.doc.status === 'Draft') {
            if (frm.doc.excel_file) {
                frm.add_custom_button(__('📋 Preview'), function() {
                    frm.trigger('show_preview');
                }, __('Actions'));
                
                frm.add_custom_button(__('✓ Validate'), function() {
                    frm.trigger('validate_items');
                }, __('Actions'));
                
                frm.add_custom_button(__('▶ Process Import'), function() {
                    frm.trigger('process_import');
                }).addClass('btn-primary');
            }
        }
        
        if (frm.doc.status === 'Processed') {
            frm.add_custom_button(__('✕ Cancel Import'), function() {
                frm.trigger('cancel_import');
            }).addClass('btn-danger');
            
            if (frm.doc.sales_invoice) {
                frm.add_custom_button(__('Sales Invoice'), function() {
                    frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
                }, __('View'));
            }
            
            if (frm.doc.stock_entry) {
                frm.add_custom_button(__('Stock Entry'), function() {
                    frappe.set_route('Form', 'Stock Entry', frm.doc.stock_entry);
                }, __('View'));
            }
        }
        
        if (frm.doc.status === 'Failed') {
            frm.add_custom_button(__('🔄 Retry'), function() {
                frm.set_value('status', 'Draft');
                frm.save().then(() => {
                    frm.trigger('process_import');
                });
            }).addClass('btn-warning');
        }
    },
    
    show_status_indicator: function(frm) {
        let status_colors = {
            'Draft': 'blue',
            'Processing': 'orange',
            'Processed': 'green',
            'Failed': 'red'
        };
        
        let color = status_colors[frm.doc.status] || 'gray';
        frm.page.set_indicator(__(frm.doc.status), color);
    },
    
    setup_realtime: function(frm) {
        frappe.realtime.on('restaurant_import_success', function(data) {
            if (data.doc_name === frm.doc.name) {
                frappe.show_alert({
                    message: __('Import muvaffaqiyatli bajarildi!'),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        });
        
        frappe.realtime.on('restaurant_import_failed', function(data) {
            if (data.doc_name === frm.doc.name) {
                frappe.msgprint({
                    title: __('Import xatosi'),
                    indicator: 'red',
                    message: data.error
                });
                frm.reload_doc();
            }
        });
    },
    
    show_preview: function(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.get_preview_data',
            args: {
                doc_name: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Excel o\'qilmoqda...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frm.trigger('render_preview_dialog', r.message);
                } else {
                    frappe.msgprint({
                        title: __('Xato'),
                        indicator: 'red',
                        message: r.message ? r.message.message : __('Preview yuklashda xato')
                    });
                }
            }
        });
    },
    
    render_preview_dialog: function(frm, data) {
        let items = data.items || [];
        let summary = data.summary || {};
        
        let rows_html = items.map((item, idx) => {
            let status_badge = item.found 
                ? `<span class="badge badge-success">${item.type}</span>`
                : `<span class="badge badge-danger">TOPILMADI</span>`;
            
            let bom_badge = item.has_bom 
                ? `<span class="badge badge-info" title="${item.bom}">BOM</span>` 
                : '';
            
            return `
                <tr class="${item.found ? '' : 'bg-danger text-white'}">
                    <td>${idx + 1}</td>
                    <td>${item.row_num}</td>
                    <td>${item.item_name}</td>
                    <td>${item.item_code || '-'}</td>
                    <td class="text-right">${item.qty}</td>
                    <td class="text-right">${format_currency(item.rate, 'UZS')}</td>
                    <td class="text-right">${format_currency(item.qty * item.rate, 'UZS')}</td>
                    <td>${status_badge} ${bom_badge}</td>
                </tr>
            `;
        }).join('');
        
        let dialog = new frappe.ui.Dialog({
            title: __('Excel Preview'),
            size: 'extra-large',
            fields: [
                {
                    fieldtype: 'HTML',
                    fieldname: 'preview_html'
                }
            ]
        });
        
        let html = `
            <div class="mb-4">
                <div class="row">
                    <div class="col-md-3">
                        <div class="stat-card bg-primary text-white p-3 rounded">
                            <h3>${summary.total_items || 0}</h3>
                            <small>Jami qatorlar</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card bg-success text-white p-3 rounded">
                            <h3>${summary.found || 0}</h3>
                            <small>Topildi</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card bg-danger text-white p-3 rounded">
                            <h3>${summary.not_found || 0}</h3>
                            <small>Topilmadi</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stat-card bg-info text-white p-3 rounded">
                            <h3>${format_currency(summary.total_amount || 0, 'UZS')}</h3>
                            <small>Jami summa</small>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="mb-3">
                <span class="badge badge-primary mr-2">Taomlar (BOM): ${summary.dishes || 0}</span>
                <span class="badge badge-secondary">Ichimliklar: ${summary.drinks || 0}</span>
            </div>
            
            <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                <table class="table table-sm table-bordered table-hover">
                    <thead class="thead-dark sticky-top">
                        <tr>
                            <th>#</th>
                            <th>Excel Row</th>
                            <th>Наименование</th>
                            <th>Item Code</th>
                            <th class="text-right">Qty</th>
                            <th class="text-right">Rate</th>
                            <th class="text-right">Amount</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows_html}
                    </tbody>
                </table>
            </div>
        `;
        
        dialog.fields_dict.preview_html.$wrapper.html(html);
        dialog.show();
    },
    
    validate_items: function(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.validate_excel_items',
            args: {
                doc_name: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Tekshirilmoqda...'),
            callback: function(r) {
                if (r.message) {
                    let data = r.message;
                    
                    if (data.success) {
                        frappe.msgprint({
                            title: __('Validation Success'),
                            indicator: 'green',
                            message: `
                                <p><strong>${data.items.length}</strong> ta item topildi</p>
                                <p>Jami: <strong>${format_currency(data.total_amount, 'UZS')}</strong></p>
                            `
                        });
                    } else {
                        let errors_html = (data.errors || []).map(e => 
                            `<li>Qator ${e.row}: ${e.error}</li>`
                        ).join('');
                        
                        frappe.msgprint({
                            title: __('Validation Errors'),
                            indicator: 'red',
                            message: `<ul>${errors_html}</ul>`
                        });
                    }
                }
            }
        });
    },
    
    process_import: function(frm) {
        frappe.confirm(
            __(`Import bajarilsinmi?<br><br>
                <strong>Company:</strong> ${frm.doc.company}<br>
                <strong>Warehouse:</strong> ${frm.doc.source_warehouse}<br>
                <strong>Date:</strong> ${frm.doc.posting_date}<br><br>
                <em>Bu jarayon Sales Invoice va Stock Entry yaratadi.</em>
            `),
            function() {
                frappe.call({
                    method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.process_import',
                    args: {
                        doc_name: frm.doc.name,
                        background: false
                    },
                    freeze: true,
                    freeze_message: __('Import jarayoni...'),
                    callback: function(r) {
                        if (r.message) {
                            let result = r.message;
                            
                            if (result.success) {
                                frappe.show_alert({
                                    message: __('Import muvaffaqiyatli!'),
                                    indicator: 'green'
                                });
                                
                                frappe.msgprint({
                                    title: __('Import natijasi'),
                                    indicator: 'green',
                                    message: `
                                        <p>✅ <strong>${result.items_count}</strong> ta item import qilindi</p>
                                        <p>💰 Jami: <strong>${format_currency(result.total_amount, 'UZS')}</strong></p>
                                        <hr>
                                        <p><a href="/app/sales-invoice/${result.sales_invoice}">
                                            📄 Sales Invoice: ${result.sales_invoice}
                                        </a></p>
                                        ${result.stock_entry ? `
                                        <p><a href="/app/stock-entry/${result.stock_entry}">
                                            📦 Stock Entry: ${result.stock_entry}
                                        </a></p>
                                        ` : ''}
                                    `
                                });
                                
                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __('Import xatosi'),
                                    indicator: 'red',
                                    message: result.message
                                });
                                frm.reload_doc();
                            }
                        }
                    }
                });
            },
            function() {}
        );
    },
    
    cancel_import: function(frm) {
        frappe.confirm(
            __('Import bekor qilinsinmi? Sales Invoice va Stock Entry ham bekor qilinadi.'),
            function() {
                frappe.call({
                    method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.cancel_import',
                    args: {
                        doc_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Bekor qilinmoqda...'),
                    callback: function(r) {
                        if (r.message) {
                            if (r.message.success) {
                                frappe.show_alert({
                                    message: __('Import bekor qilindi'),
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: __('Xato'),
                                    indicator: 'red',
                                    message: r.message.message
                                });
                            }
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    }
});