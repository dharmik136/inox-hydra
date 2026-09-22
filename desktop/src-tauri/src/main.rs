// Windows subsystem in release, so launching the application does not also
// open a console window behind it.
//
// Note what this costs: in a release build there is no stderr, so anything the
// shell prints about a failed start goes nowhere. Debug builds keep a console
// and do show it. Surfacing start failures to a release user is tracked
// separately and is not solved by this attribute.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    linkedin_studio_desktop_lib::run();
}
