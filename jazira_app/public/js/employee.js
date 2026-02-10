frappe.ui.form.on('Employee', {
    refresh: function(frm) {
        simplify_for_manager(frm);
    },
    
    onload: function(frm) {
        simplify_for_manager(frm);
    },
    
    after_save: function(frm) {
        simplify_for_manager(frm);
    }
});

function simplify_for_manager(frm) {
    // Administrator va admin_jazira - to'liq forma
    const full_access_users = ["Administrator", "admin_jazira@jazira.uz"];
    if (full_access_users.includes(frappe.session.user)) {
        return;
    }
    
    // ═══════════════════════════════════════════════════════════════
    // KERAKLI FIELDLAR
    // ═══════════════════════════════════════════════════════════════
    const required_fields = [
        // Shaxsiy
        'naming_series', 'first_name', 'middle_name', 'last_name',
        'employee_name', 'gender', 'date_of_birth', 'date_of_joining', 
        'status', 'image',
        
        // Kompaniya
        'company', 'designation',
        
        // Davomat
        'attendance_device_id', 'default_shift',
        
        // Maosh
        'hourly_rate',
        
        // Aloqa
        'cell_number', 'personal_email'
    ];
    
    // ═══════════════════════════════════════════════════════════════
    // BARCHA FIELDLARNI YASHIRISH (keraklilaridan tashqari)
    // ═══════════════════════════════════════════════════════════════
    frm.meta.fields.forEach(function(field) {
        if (field.fieldname && field.fieldtype !== 'Section Break' && field.fieldtype !== 'Column Break') {
            if (!required_fields.includes(field.fieldname)) {
                frm.set_df_property(field.fieldname, 'hidden', 1);
            }
        }
    });
    
    // ═══════════════════════════════════════════════════════════════
    // TABLARNI YASHIRISH
    // ═══════════════════════════════════════════════════════════════
    // Overview dan boshqa barcha tablarni yashirish
    setTimeout(function() {
        // Tab containerini topish
        const tabs = frm.page.wrapper.find('.form-tabs .nav-item');
        const allowed_tabs = ['Overview', 'Asosiy']; // Faqat birinchi tab
        
        tabs.each(function() {
            const tab_label = $(this).find('.nav-link').text().trim();
            if (!allowed_tabs.includes(tab_label) && tab_label !== '') {
                $(this).hide();
            }
        });
    }, 100);
    
    // ═══════════════════════════════════════════════════════════════
    // SECTION BREAK'LARNI TARTIBGA SOLISH
    // ═══════════════════════════════════════════════════════════════
    
    // Ortiqcha section'larni yashirish
    const sections_to_hide = [
        'user_details_section',
        'address_contacts_tab',
        'attendance_and_leave_details',
        'salary_details',
        'personal_details',
        'educational_qualification',
        'previous_work_experience',
        'exit',
        'sb_health'
    ];
    
    sections_to_hide.forEach(function(section) {
        if (frm.fields_dict[section]) {
            $(frm.fields_dict[section].wrapper).hide();
        }
    });
}