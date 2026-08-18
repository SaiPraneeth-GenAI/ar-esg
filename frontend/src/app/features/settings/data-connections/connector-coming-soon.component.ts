import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CategoryIconComponent } from './category-icon.component';
import { Connector, getConnector } from './connectors.data';

@Component({
  selector: 'app-connector-coming-soon',
  standalone: true,
  imports: [RouterLink, CategoryIconComponent],
  templateUrl: './connector-coming-soon.component.html',
  styleUrl: './connector-coming-soon.component.css'
})
export class ConnectorComingSoonComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  connector = signal<Connector | null>(null);
  requested = signal(false);

  readonly ready = ['Data model', 'Mapping framework', 'Validation framework'];
  readonly upcoming = ['Production connector', 'Authentication', 'Live synchronization'];

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    const found = getConnector(id);
    if (!found) {
      this.router.navigateByUrl('/admin/settings/data-connections');
      return;
    }
    this.connector.set(found);
  }

  requestConnector(): void {
    this.requested.set(true);
  }
}
