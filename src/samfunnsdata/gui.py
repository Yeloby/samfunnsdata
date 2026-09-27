import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from . import gui_work
from .gui_jobs import GuiJobs
from .navigation import install_navigation, text_window
from .questions import (
    ElectionComparisonQuestion,
    ElectionQuestion,
    ExchangeQuestion,
    MunicipalElectionComparisonQuestion,
    MunicipalElectionQuestion,
    PopulationQuestion,
    RateQuestion,
    UnemploymentQuestion,
    parse_question,
)


class SamfunnsdataWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(
            application=app,
            title="Samfunnsdata",
        )

        self.set_default_size(1000, 760)

        self.current_series = []
        self.current_kind = None
        self.current_result = None

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        self.set_child(box)

        title = Gtk.Label()
        title.set_markup(
            "<span size='xx-large' weight='bold'>"
            "Samfunnsdata"
            "</span>"
        )
        title.set_xalign(0)
        box.append(title)

        subtitle = Gtk.Label(
            label="Offentlige data. Etterprøvbare svar."
        )
        subtitle.set_xalign(0)
        box.append(subtitle)

        question_label = Gtk.Label(
            label="Hva vil du finne ut?"
        )
        question_label.set_xalign(0)
        box.append(question_label)

        question_form = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
        )
        box.append(question_form)

        self.question = Gtk.Entry()
        self.question.set_placeholder_text(
            "F.eks. Sammenlign Trondheim og Bergen siden 2000"
        )
        self.question.set_hexpand(True)
        self.question.connect(
            "activate",
            self.on_question,
        )
        question_form.append(self.question)

        question_button = Gtk.Button(
            label="Analyser spørsmål"
        )
        question_button.connect(
            "clicked",
            self.on_question,
        )
        question_form.append(question_button)

        advanced_label = Gtk.Label(
            label="Manuelle valg"
        )
        advanced_label.set_xalign(0)
        box.append(advanced_label)

        form = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
        )
        box.append(form)

        self.place = Gtk.Entry()
        self.place.set_placeholder_text(
            "Kommune, f.eks. Trondheim"
        )
        self.place.set_hexpand(True)
        form.append(self.place)

        self.compare_place = Gtk.Entry()
        self.compare_place.set_placeholder_text(
            "Sammenlign med, f.eks. Bergen"
        )
        self.compare_place.set_hexpand(True)
        form.append(self.compare_place)

        self.since = Gtk.Entry()
        self.since.set_placeholder_text("Fra år")
        self.since.set_width_chars(8)
        form.append(self.since)

        button = Gtk.Button(label="Analyser")
        button.connect("clicked", self.on_analyze)
        form.append(button)

        self.status = Gtk.Label()
        self.status.set_xalign(0)
        self.status.set_wrap(True)
        box.append(self.status)

        self.result = Gtk.Label()
        self.result.set_xalign(0)
        self.result.set_yalign(0)
        self.result.set_wrap(True)
        self.result.set_selectable(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
        )
        content.append(self.result)

        self.chart = Gtk.Picture()
        self.chart.set_can_shrink(True)
        self.chart.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.chart.set_size_request(-1, 360)
        self.chart.set_hexpand(True)
        self.chart.set_vexpand(True)
        self.chart.set_visible(False)
        content.append(self.chart)

        scroll.set_child(content)
        box.append(scroll)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
        )
        box.append(actions)

        self.raw_button = Gtk.Button(label="Vis rådata")
        self.raw_button.set_sensitive(False)
        self.raw_button.connect("clicked", self.on_show_raw)
        actions.append(self.raw_button)

        self.export_button = Gtk.Button(label="Eksporter CSV")
        self.export_button.set_sensitive(False)
        self.export_button.connect("clicked", self.on_export)
        actions.append(self.export_button)

        self.receipt_button = Gtk.Button(label="Vis datakvittering")
        self.receipt_button.set_sensitive(False)
        self.receipt_button.connect("clicked", self.on_show_receipt)
        actions.append(self.receipt_button)
        self.receipt_export_button = Gtk.Button(label="Eksporter kvittering (JSON)")
        self.receipt_export_button.set_sensitive(False)
        self.receipt_export_button.connect("clicked", self.on_export_receipt)
        actions.append(self.receipt_export_button)

        self.source = Gtk.Label(
            label=(
                "Kilde: Statistisk sentralbyrå · "
                "Tabell 07459"
            )
        )
        self.source.set_xalign(0)
        box.append(self.source)
        self.source.set_text("")
        self.spinner = Gtk.Spinner()
        self.cancel_button = Gtk.Button(label="Avbryt")
        self.cancel_button.set_sensitive(False)
        self.cancel_button.connect("clicked", self.on_cancel)
        actions.append(self.spinner)
        actions.append(self.cancel_button)
        self.jobs = GuiJobs(self._set_busy, self.status.set_text)
        self.connect("close-request", self._on_close)
        self.connect("unrealize", lambda *_: self.jobs.close())
        install_navigation(self, box, (advanced_label, form))

    def _set_busy(self, busy):
        self.spinner.set_spinning(busy)
        self.cancel_button.set_sensitive(busy)
        available = bool(self.current_series) and not busy
        self.raw_button.set_sensitive(available)
        self.export_button.set_sensitive(available)
        self.receipt_button.set_sensitive(self.current_result is not None and not busy)
        self.receipt_export_button.set_sensitive(self.current_result is not None and not busy)
        if busy:
            self.status.set_text("Henter og analyserer data …")

    def on_cancel(self, _button):
        self.jobs.cancel()
        self.status.set_text("Avbrutt. Et pågående kildekall kan fortsatt fullføres.")

    def _on_close(self, *_args):
        self.jobs.close()
        return False

    def destroy(self):
        self.jobs.close()
        super().destroy()

    def _apply_analysis(self, view):
        self.jobs._assert_owner()
        texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(view["chart"]))
        markup, text = view["result"]
        if markup:
            self.result.set_markup(text)
        else:
            self.result.set_text(text)
        self.status.set_text(view["status"])
        self.source.set_text(view["source"])
        self.current_series = view["series"]
        self.current_kind = view["kind"]
        self.current_result = view.get("analysis_result")
        self.chart.set_paintable(texture)
        self.chart.set_visible(True)

    def on_question(self, button):
        self.jobs.cancel()
        try:
            question = parse_question(
                self.question.get_text()
            )
        except ValueError as error:
            self.status.set_text(str(error))
            return

        if isinstance(question, ExchangeQuestion):
            self.jobs.submit(lambda token: gui_work.exchange_question(token, question), self._apply_analysis)
            return
        if isinstance(question, RateQuestion):
            self.jobs.submit(lambda token: gui_work.rate_question(token, question), self._apply_analysis)
            return

        if isinstance(question, UnemploymentQuestion):
            self.on_unemployment_question(question)
            return

        if isinstance(question, PopulationQuestion):
            self.place.set_text(question.place)
            self.compare_place.set_text(
                question.compare_place or ""
            )
            self.since.set_text(
                str(question.since)
                if question.since is not None
                else ""
            )
            self.on_analyze(button)
            return

        if isinstance(question, ElectionComparisonQuestion):
            self.on_election_comparison(question)
            return

        if isinstance(
            question,
            MunicipalElectionComparisonQuestion,
        ):
            self.on_municipal_election_comparison(question)
            return

        if isinstance(question, MunicipalElectionQuestion):
            self.on_municipal_election_question(question)
            return

        if isinstance(question, ElectionQuestion):
            self.on_election_question(question)
            return

    def on_unemployment_question(self, question):
        self.jobs.submit(lambda token: gui_work.unemployment_question(token, question),
                         self._apply_analysis)

    def on_election_comparison(self, question):
        self.jobs.submit(lambda token: gui_work.election_comparison(token, question),
                         self._apply_analysis)

    def on_municipal_election_comparison(self, question):
        self.jobs.submit(lambda token: gui_work.municipal_election_comparison(token, question),
                         self._apply_analysis)

    def on_municipal_election_question(self, question):
        self.jobs.submit(lambda token: gui_work.municipal_election_question(token, question),
                         self._apply_analysis)

    def on_election_question(self, question):
        self.jobs.submit(lambda token: gui_work.election_question(token, question),
                         self._apply_analysis)

    def on_analyze(self, button):
        self.jobs.cancel()
        place = self.place.get_text().strip()
        compare_place = self.compare_place.get_text().strip()
        since_text = self.since.get_text().strip()
        if not place:
            self.status.set_text("Skriv inn en kommune.")
            return
        try:
            since = int(since_text) if since_text else None
        except ValueError:
            self.status.set_text("År må være et heltall.")
            return
        self.jobs.submit(lambda token: gui_work.population(token, place, compare_place, since),
                         self._apply_analysis)

    def on_show_raw(self, button):
        if not self.current_series:
            return

        kind, series = self.current_kind, list(self.current_series)
        previous_status = self.status.get_text()

        def show(prepared):
            self._show_raw(prepared)
            self.status.set_text(previous_status)

        self.jobs.submit(lambda token: gui_work.raw_text(token, kind, series), show)

    def _show_raw(self, prepared):
        raw_text, source_text = prepared
        window = Gtk.Window(
            title="Rådata",
            transient_for=self,
            destroy_with_parent=True,
            modal=False,
        )
        window.set_default_size(760, 600)

        outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )
        outer.set_margin_top(18)
        outer.set_margin_bottom(18)
        outer.set_margin_start(18)
        outer.set_margin_end(18)
        window.set_child(outer)

        title = Gtk.Label()
        title.set_markup(
            "<span size='x-large' weight='bold'>"
            "Rådata"
            "</span>"
        )
        title.set_xalign(0)
        outer.append(title)

        text = Gtk.TextView()
        text.set_editable(False)
        text.set_cursor_visible(False)
        text.set_monospace(True)

        text.get_buffer().set_text(raw_text)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_child(text)
        outer.append(scroll)

        source = Gtk.Label(label=source_text)
        source.set_xalign(0)
        outer.append(source)

        window.present()

    def on_show_receipt(self, _button):
        if self.current_result is None:
            return
        receipt = self.current_result.receipt
        previous_status = self.status.get_text()

        def show(text):
            text_window(self, "Datakvittering", text)
            self.status.set_text(previous_status)

        self.jobs.submit(lambda token: gui_work.receipt_text(token, receipt), show)

    def on_export_receipt(self, _button):
        if self.current_result is None:
            return
        receipt = self.current_result.receipt
        generation = self.jobs.generation
        dialog = Gtk.FileDialog()
        dialog.set_title("Eksporter datakvittering som JSON")
        dialog.set_initial_name("samfunnsdata.receipt.json")
        dialog.save(self, None, lambda dialog, result:
                    self.on_receipt_export_finished(dialog, result, receipt, generation))

    def on_receipt_export_finished(self, dialog, result, receipt, generation):
        if self.jobs.closed or generation != self.jobs.generation:
            return
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        if file is None:
            return
        path = file.get_path()
        if path is None:
            self.status.set_text("Kan bare eksportere til en lokal fil.")
            return
        self.jobs.submit(lambda token: gui_work.export_receipt(token, receipt, path),
                         self.status.set_text)

    def on_export(self, button):
        if not self.current_series:
            return

        dialog = Gtk.FileDialog()
        dialog.set_title("Eksporter CSV")
        dialog.set_initial_name("samfunnsdata.csv")

        snapshot = (self.current_kind, list(self.current_series))
        generation = self.jobs.generation
        dialog.save(
            self, None,
            lambda dialog, result: self.on_export_finished(dialog, result, snapshot, generation),
        )

    def on_export_finished(self, dialog, result, snapshot=None, generation=None):
        if self.jobs.closed or (generation is not None and generation != self.jobs.generation):
            return
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return

        if file is None:
            return

        path = file.get_path()

        if path is None:
            self.status.set_text(
                "Kan bare eksportere til en lokal fil."
            )
            return

        kind, series = snapshot or (self.current_kind, list(self.current_series))
        self.jobs.submit(lambda token: gui_work.export_csv(token, kind, series, path),
                         self.status.set_text)


class SamfunnsdataApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.Yeloby.Samfunnsdata"
        )

    def do_activate(self):
        window = SamfunnsdataWindow(self)
        window.present()


def main():
    app = SamfunnsdataApp()
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
