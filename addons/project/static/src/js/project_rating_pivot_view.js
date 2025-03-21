/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { PivotArchParser } from "@web/views/pivot/pivot_arch_parser";
import { PivotView } from "@web/views/pivot/pivot_view";

const viewRegistry = registry.category("views");

const MEASURE_STRINGS = {
    parent_res_id: _lt("Project"),
    rating: _lt("Rating Value (/5)"),
    res_id: _lt("Task"),
};

class ProjectRatingArchParser extends PivotArchParser {
    parse() {
        const archInfo = super.parse(...arguments);
        for (const [key, val] of Object.entries(MEASURE_STRINGS)) {
            archInfo.fieldAttrs[key] = {
                ...archInfo.fieldAttrs[key],
                string: val.toString(),
            };
        }
        return archInfo;
    }
}

// Would it be not better achiedved by using a proper arch directly?

class ProjectRatingPivotView extends PivotView {}
ProjectRatingPivotView.ArchParser = ProjectRatingArchParser;

viewRegistry.add("project_rating_pivot", ProjectRatingPivotView);
